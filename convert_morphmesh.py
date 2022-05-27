#!/usr/bin/python3
import os
import sys
import struct
import math
from argparse import ArgumentParser

# fileId, fileVersion, offset, count
MULTI_HEADER_STRUCT_SIZE = 16
# meshOffset, meshId, padding
MULTI_ENTRY_STRUCT_SIZE = 16
# fileId, fileVersion, flags, size
MESH_HEADER_STRUCT_SIZE = 12
# vertexBuffer, indexBuffer, subsets, joints, drawMode, winding
MESH_STRUCT_SIZE = 56
# vertex buffer entry list: nameOffset, componentType, componentCount, offset
VERTEX_BUFFER_ENTRY_STRUCT_SIZE = 16
# subset list: count, offset, minXYZ, maxXYZ, nameOffset, nameLength
SUBSET_STRUCT_SIZE_V3_V4 = 40;
# subset list: count, offset, minXYZ, maxXYZ, nameOffset, nameLength, lightmapSizeWidth, lightmapSizeHeight
SUBSET_STRUCT_SIZE_V5 = 48;

def read_qq3d_file_header(f):
    res = {}
    f.seek(-MULTI_HEADER_STRUCT_SIZE, os.SEEK_END)
    r = f.read(MULTI_HEADER_STRUCT_SIZE)
    fileId, fileVersion, unused, count = struct.unpack_from('<IIII', r, 0)
    if fileId != 555777497 or fileVersion != 1:
        sys.exit("Invalid multi header!")

    for i in range(count):
        f.seek(-MULTI_HEADER_STRUCT_SIZE - (MULTI_ENTRY_STRUCT_SIZE * count) \
                                         + (MULTI_ENTRY_STRUCT_SIZE * i), os.SEEK_END)
        r = f.read(MULTI_ENTRY_STRUCT_SIZE)
        offset, meshId = struct.unpack_from('<QI', r, 0);
        res[meshId] = offset
    return res

#     enum class ComponentType {
#        UnsignedInt8 = 1,
#        Int8,
#        UnsignedInt16,
#        Int16,
#        UnsignedInt32,
#        Int32,
#        UnsignedInt64,
#        Int64,
#        Float16,
#        Float32,
#        Float64
#    };
bytesSize4ComponentType = [0, 1, 1, 2, 2, 4, 4, 8, 8, 2, 4, 8]

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("-i", "--input", dest="input",
                        help="A mesh file for conversion", metavar="INPUT")
    parser.add_argument("-o", "--output", dest="output",
                        help="A filename for output", metavar="OUTPUT")
    args = parser.parse_args()

    with open(args.input, "rb") as fsrc, open(args.output, "wb") as fdst:
        meshInfo = read_qq3d_file_header(fsrc)
        newMeshInfo = {}
        for k, v in meshInfo.items():
            # readMeshData
            fsrc.seek(v)
            r = fsrc.read(MESH_HEADER_STRUCT_SIZE)
            fileId, fileVersion, flags, sizeInBytes = struct.unpack_from('<IHHI', r, 0)
            print("sizeInBytes", sizeInBytes)

            if fileId != 3365961549 or fileVersion < 3 or fileVersion > 5:
                sys.exit("Invalid mesh data header!")

            r = fsrc.read(MESH_STRUCT_SIZE)
            targetBufferEntriesCount = 0
            vertexBufferEntriesCount, vertexBufferStride = struct.unpack_from('<II', r, 4)
            vertexBufferDataSize, = struct.unpack_from('<I', r, 16)
            indexBufferCompType, indexBufferDataOffset, indexBufferDataSize = struct.unpack_from('<III', r, 20)
            subsetCount, = struct.unpack_from('<I', r, 36)
            drawMode, winding = struct.unpack_from('<II', r, 48)

            #assert(fdst.tell() == v)
            oldEntries = []
            BUFFER_ENTRY_COMPONENT_TYPE = 0
            BUFFER_ENTRY_COMPONENT_COUNT = 1
            BUFFER_ENTRY_OFFSET = 2
            BUFFER_ENTRY_NAME = 3
            BUFFER_ENTRY_TARGETID = 4
            for i in range(vertexBufferEntriesCount):
                r = fsrc.read(VERTEX_BUFFER_ENTRY_STRUCT_SIZE)
                componentType, componentCount, offset = struct.unpack_from('<III', r, 4)
                oldEntries.append([componentType, componentCount, offset])
            fsrc.seek((4 - (VERTEX_BUFFER_ENTRY_STRUCT_SIZE * vertexBufferEntriesCount) % 4), os.SEEK_CUR)

            vEntries = []
            tEntries = []
            newVBufStride = 0
            for entry in oldEntries:
                r = fsrc.read(4)
                nameLength, = struct.unpack_from('<I', r, 0)
                name = fsrc.read(nameLength)
                if name[:6] == b'attr_t':
                    targetId = int(name[-2:-1], 10)
                    if targetId == 0:
                        targetBufferEntriesCount = targetBufferEntriesCount + 1
                    newName = name[:5] + name[6:-2] + name[-1:]
                    entry.append(newName)
                    entry.append(targetId)
                    tEntries.append(entry)
                else:
                    entry.append(name)
                    vEntries.append(entry)
                    newVBufStride += bytesSize4ComponentType[entry[BUFFER_ENTRY_COMPONENT_TYPE]] * entry[BUFFER_ENTRY_COMPONENT_COUNT]
                fsrc.seek((4 - nameLength % 4), os.SEEK_CUR)

            #print('vEntries', vEntries)
            #print('tEntries', tEntries)
            print(targetBufferEntriesCount)

            if not tEntries:
                # FIXME support to convert anyway
                sys.exit("There is no morph target in this mesh. It is not necessary to convert.")

            vertexBufferData = fsrc.read(vertexBufferDataSize)
            #r = fsrc.read(4 - vertexBufferDataSize % 4)
            fsrc.seek((4 - vertexBufferDataSize % 4), os.SEEK_CUR)

            indexBufferData = fsrc.read(indexBufferDataSize)
            #r = fsrc.read(4 - indexBufferDataSize % 4)
            fsrc.seek((4 - indexBufferDataSize % 4), os.SEEK_CUR)

            # packed_data, nameLength, name
            subsets = []
            subsetBytesSize = 0;
            for i in range(subsetCount):
                r = fsrc.read(SUBSET_STRUCT_SIZE_V3_V4)
                #curSubsetCount, curSubsetOffset, minX, minY, minZ, maxX, maxY, maxZ, nameOffset, nameLength \
                #    = struct.unpack_from('<IIffffffII', r, 0)
                #print(curSubsetCount, curSubsetOffset, minX, minY, minZ, maxX, maxY, maxZ, nameOffset, nameLength)
                nameLength, = struct.unpack_from('<I', r, 36)
                subsetBytesSize += SUBSET_STRUCT_SIZE_V3_V4
                if fileVersion == 5:
                    r += fsrc.read(SUBSET_STRUCT_SIZE_V5 - SUBSET_STRUCT_SIZE_V3_V4)
                    subsetByteSize += (SUBSET_STRUCT_SIZE_V5 - SUBSET_STRUCT_SIZE_V3_V4)
                else:
                    r += struct.pack('<II', 0, 0)
                subsets.append([r, nameLength])
            fsrc.seek((4 - subsetBytesSize % 4), os.SEEK_CUR)

            for subset in subsets:
                r = fsrc.read(subset[1] * 2) # UTF_16_le
                subset.append(r)
                fsrc.seek((4 - (subset[1] * 2) % 4), os.SEEK_CUR)

            vertexCount = int(vertexBufferDataSize / vertexBufferStride);
            #print('vertexCount', vertexCount)
            newVertexBufferData = b''
            for i in range(vertexCount):
                for entry in vEntries:
                    readStart = entry[BUFFER_ENTRY_OFFSET] + i * vertexBufferStride
                    componentByteSize = bytesSize4ComponentType[entry[BUFFER_ENTRY_COMPONENT_TYPE]] * entry[BUFFER_ENTRY_COMPONENT_COUNT]
                    readEnd = readStart + componentByteSize
                    newVertexBufferData += vertexBufferData[readStart:readEnd]

            targetCount = int(len(tEntries) / targetBufferEntriesCount)
            targetDataSizePerComponent = 4 * 4 * vertexCount
            targetDataWidth = math.ceil(math.sqrt(vertexCount))
            newTargetDataSizePerComponent = targetDataWidth * targetDataWidth * 4 * 4
            newTargetBufferData = b''
            # assuming all the data sorted by targetId( exactly we made them previously )
            dict_tEntries_sort = { b'attr_pos\x00': 0,
                                   b'attr_norm\x00': 1,
                                   b'attr_uv0\x00': 2,
                                   b'attr_textan\x00': 3,
                                   b'attr_binormal\x00': 4,
                                   b'attr_color\x00': 5,
                                   b'attr_uv1\x00': 6 }
            tEntries.sort(key=lambda x: dict_tEntries_sort[x[BUFFER_ENTRY_NAME]])
            for entry in tEntries:
                newOffset = len(newTargetBufferData)
                for i in range(vertexCount):
                    readStart = entry[BUFFER_ENTRY_OFFSET] + i * vertexBufferStride
                    componentByteSize = bytesSize4ComponentType[entry[BUFFER_ENTRY_COMPONENT_TYPE]] * entry[BUFFER_ENTRY_COMPONENT_COUNT]
                    readEnd = readStart + componentByteSize
                    newTargetBufferData += vertexBufferData[readStart:readEnd]
                    # padding
                    newTargetBufferData += b'\x00' * (16 - componentByteSize)
                # padding
                newTargetBufferData += b'\x00' * (newTargetDataSizePerComponent - targetDataSizePerComponent)
                entry[BUFFER_ENTRY_OFFSET] = newOffset

            newMeshInfo[k] = fdst.tell()

            # Write a dummy header with 0 size
            #wData = struct.pack('<IHHI', fileId, 6, flags, 0)
            #fdst.write(wData)
            fdst.seek(MESH_HEADER_STRUCT_SIZE, os.SEEK_CUR)
            #wData = struct.pack('<IIIII', len(tEntries), len(vEntries), newVBufStride, len(newTargetBufferData), len(newVertexBufferData))
            wData = struct.pack('<IIIII', targetBufferEntriesCount, len(vEntries), newVBufStride, len(newTargetBufferData), len(newVertexBufferData))
            fdst.write(wData)
            wData = struct.pack('<III', indexBufferCompType, 0, indexBufferDataSize)
            fdst.write(wData)
            wData = struct.pack('<IIIIII', targetCount, subsetCount, 0, 0, drawMode, winding)
            fdst.write(wData)
            for entry in vEntries:
                wData = struct.pack('<IIII', 0, entry[BUFFER_ENTRY_COMPONENT_TYPE],\
                                                entry[BUFFER_ENTRY_COMPONENT_COUNT],\
                                                entry[BUFFER_ENTRY_OFFSET])
                fdst.write(wData)
            #fdst.write(b'\00' * (4 - (VERTEX_BUFFER_ENTRY_STRUCT_SIZE * len(vEntries)) % 4))
            fdst.seek((4 - (VERTEX_BUFFER_ENTRY_STRUCT_SIZE * len(vEntries)) % 4), os.SEEK_CUR)

            for entry in vEntries:
                fdst.write(struct.pack('<I', len(entry[BUFFER_ENTRY_NAME])))
                fdst.write(entry[BUFFER_ENTRY_NAME])
                #fdst.write(b'\00' * (4 - (len(entry[BUFFER_ENTRY_NAME])) % 4))
                fdst.seek((4 - (len(entry[BUFFER_ENTRY_NAME])) % 4), os.SEEK_CUR)

            fdst.write(newVertexBufferData)
            fdst.seek((4 - (len(newVertexBufferData)) % 4), os.SEEK_CUR)
            fdst.write(indexBufferData)
            fdst.seek((4 - (len(indexBufferData)) % 4), os.SEEK_CUR)

            for subset in subsets:
                fdst.write(subset[0])
            fdst.seek((4 - (SUBSET_STRUCT_SIZE_V5 * (len(subsets))) % 4), os.SEEK_CUR)

            for subset in subsets:
                fdst.write(subset[2])
                fdst.seek((4 - (subset[1] * 2) % 4), os.SEEK_CUR)

            # Morph Target Data
            for entry in tEntries:
                if entry[BUFFER_ENTRY_TARGETID] == 0:
                    wData = struct.pack('<IIII', 0, entry[BUFFER_ENTRY_COMPONENT_TYPE],\
                                                    entry[BUFFER_ENTRY_COMPONENT_COUNT],\
                                                    entry[BUFFER_ENTRY_OFFSET])
                    fdst.write(wData)
            fdst.seek((4 - (VERTEX_BUFFER_ENTRY_STRUCT_SIZE * targetBufferEntriesCount) % 4), os.SEEK_CUR)
            for entry in tEntries:
                if entry[BUFFER_ENTRY_TARGETID] == 0:
                    fdst.write(struct.pack('<I', len(entry[BUFFER_ENTRY_NAME])))
                    fdst.write(entry[BUFFER_ENTRY_NAME])
                    fdst.seek((4 - (len(entry[BUFFER_ENTRY_NAME])) % 4), os.SEEK_CUR)

            fdst.write(newTargetBufferData)

            endPos = fdst.tell()
            sizeInBytes = endPos - meshInfo[k] - MESH_HEADER_STRUCT_SIZE
            #print(newMeshInfo)
            fdst.seek(newMeshInfo[k], os.SEEK_SET)
            wData = struct.pack('<IHHI', fileId, 6, flags, sizeInBytes)
            fdst.write(wData)

            fdst.seek(endPos, os.SEEK_SET)

        for k, v in newMeshInfo.items():
            fdst.write(struct.pack('<QII', v, k, 0))

        fdst.write(struct.pack('<IIII', 555777497, 1, endPos, len(newMeshInfo)))
