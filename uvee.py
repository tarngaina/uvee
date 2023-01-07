from os import mkdir, walk
from os.path import basename, dirname, exists, isdir
from sys import argv
from PIL import Image, ImageDraw
from struct import Struct


class Vector:
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x, y, z=None):
        self.x = x
        self.y = y
        self.z = z


class BinaryStream:
    struct_int16 = Struct('h')
    struct_uint16 = Struct('H')
    struct_int32 = Struct('i')
    struct_uint32 = Struct('I')
    struct_float = Struct('f')
    struct_vec2 = Struct('2f')
    struct_vec3 = Struct('3f')
    struct_quat = Struct('4f')

    def __init__(self, f):
        self.stream = f

    # stuffs
    def seek(self, pos, mode=0):
        self.stream.seek(pos, mode)

    def tell(self):
        return self.stream.tell()

    def pad(self, length):
        self.stream.seek(length, 1)
        return None

    def end(self):
        cur = self.stream.tell()
        self.stream.seek(0, 2)
        res = self.stream.tell()
        self.stream.seek(cur)
        return res

    # reads
    def read_byte(self):
        return self.stream.read(1)

    def read_bytes(self, length):
        return self.stream.read(length)

    def read_int16(self, count=1):
        if count > 1:
            return Struct(f'{count}h').unpack(self.stream.read(2*count))
        return BinaryStream.struct_int16.unpack(self.stream.read(2))[0]

    def read_uint16(self, count=1):
        if count > 1:
            return Struct(f'{count}H').unpack(self.stream.read(2*count))
        return BinaryStream.struct_uint16.unpack(self.stream.read(2))[0]

    def read_int32(self, count=1):
        if count > 1:
            return Struct(f'{count}i').unpack(self.stream.read(4*count))
        return BinaryStream.struct_int32.unpack(self.stream.read(4))[0]

    def read_uint32(self, count=1):
        if count > 1:
            return Struct(f'{count}I').unpack(self.stream.read(4*count))
        return BinaryStream.struct_uint32.unpack(self.stream.read(4))[0]

    def read_float(self, count=1):
        if count > 1:
            return Struct(f'{count}f').unpack(self.stream.read(4*count))
        return BinaryStream.struct_float.unpack(self.stream.read(4))[0]

    def read_vec2(self, count=1):
        if count > 1:
            floats = Struct(f'{count*2}f').unpack(self.stream.read(8*count))
            return [Vector(floats[i], floats[i+1]) for i in range(0, len(floats), 2)]
        return Vector(*BinaryStream.struct_vec2.unpack(self.stream.read(8)))

    def read_vec3(self, count=1):
        if count > 1:
            floats = Struct(f'{count*3}f').unpack(self.stream.read(12*count))
            return [Vector(floats[i], floats[i+1], floats[i+2]) for i in range(0, len(floats), 3)]
        return Vector(*BinaryStream.struct_vec3.unpack(self.stream.read(12)))

    def read_ascii(self, length):
        return self.stream.read(length).decode('ascii')

    def read_padded_ascii(self, length):
        return bytes(b for b in self.stream.read(length) if b != 0).decode('ascii')

    def read_char_until_zero(self):
        s = ''
        while True:
            c = self.stream.read(1)[0]
            if c == 0:
                break
            s += chr(c)
        return s

    # writes
    def write_bytes(self, bytes):
        self.stream.write(bytes)

    def write_int16(self, *values):
        count = len(values)
        if count > 1:
            self.stream.write(Struct(f'{count}h').pack(*values))
            return
        self.stream.write(BinaryStream.struct_int16.pack(values[0]))

    def write_uint16(self, *values):
        count = len(values)
        if count > 1:
            self.stream.write(Struct(f'{count}H').pack(*values))
            return
        self.stream.write(BinaryStream.struct_uint16.pack(values[0]))

    def write_int32(self, *values):
        count = len(values)
        if count > 1:
            self.stream.write(Struct(f'{count}i').pack(*values))
            return
        self.stream.write(BinaryStream.struct_int32.pack(values[0]))

    def write_uint32(self, *values):
        count = len(values)
        if count > 1:
            self.stream.write(Struct(f'{count}I').pack(*values))
            return
        self.stream.write(BinaryStream.struct_uint32.pack(values[0]))

    def write_float(self, *values):
        count = len(values)
        if count > 1:
            self.stream.write(Struct(f'{count}f').pack(*values))
            return
        self.stream.write(BinaryStream.struct_float.pack(values[0]))

    def write_vec2(self, *vec2s):
        count = len(vec2s)
        if count > 1:
            floats = [value for vec in vec2s for value in vec]
            self.stream.write(Struct(f'{len(floats)}f').pack(*floats))
            return
        self.stream.write(BinaryStream.struct_vec2.pack(*vec2s[0]))

    def write_vec3(self, *vec3s):
        count = len(vec3s)
        if count > 1:
            floats = [value for vec in vec3s for value in vec]
            self.stream.write(Struct(f'{len(floats)}f').pack(*floats))
            return
        self.stream.write(BinaryStream.struct_vec3.pack(*vec3s[0]))

    def write_ascii(self, value):
        self.stream.write(value.encode('ascii'))

    def write_padded_ascii(self, length, value):
        self.stream.write(
            value.encode('ascii') + bytes([0])*(length-len(value)))


class SKNVertex:
    __slots__ = (
        'position', 'influences', 'weights', 'normal', 'uv'
    )

    def __init__(self):
        self.position = None
        self.influences = None
        self.weights = None
        self.normal = None
        self.uv = None


class SKNSubmesh:
    __slots__ = (
        'name', 'vertex_start', 'vertex_count', 'index_start', 'index_count'
    )

    def __init__(self):
        self.name = None
        self.vertex_start = None
        self.vertex_count = None
        self.index_start = None
        self.index_count = None


class SKN:
    def __init__(self):
        self.indices = []
        self.vertices = []
        self.submeshes = []

    def read(self, path):
        with open(path, 'rb') as f:
            bs = BinaryStream(f)

            magic = bs.read_uint32()
            if magic != 0x00112233:
                raise Exception(
                    f'[SKN.read()]: Wrong signature file: {magic}')

            major, minor = bs.read_uint16(2)
            if major not in (0, 2, 4) and minor != 1:
                raise Exception(
                    f'[SKN.read()]: Unsupported file version: {major}.{minor}')

            vertex_type = 0
            if major == 0:
                # version 0 doesn't have submesh data
                index_count, vertex_count = bs.read_uint32(2)

                submesh = SKNSubmesh()
                submesh.name = 'Base'
                submesh.vertex_start = 0
                submesh.vertex_count = vertex_count
                submesh.index_start = 0
                submesh.index_count = index_count
                self.submeshes.append(submesh)
            else:
                # read submeshes
                submesh_count = bs.read_uint32()
                self.submeshes = [SKNSubmesh() for i in range(submesh_count)]
                for i in range(submesh_count):
                    submesh = self.submeshes[i]
                    submesh.name = bs.read_padded_ascii(64)
                    submesh.vertex_start, submesh.vertex_count, submesh.index_start, submesh.index_count = bs.read_uint32(
                        4)

                if major == 4:
                    bs.pad(4)  # flags

                index_count, vertex_count = bs.read_uint32(2)

                # pad all this, cause we dont need
                if major == 4:
                    bs.pad(4)  # vertex size
                    vertex_type = bs.read_uint32()
                    # bouding box: 2 vec3 min-max
                    bs.pad(24)
                    # bouding sphere: vec3 central + float radius
                    bs.pad(16)

            if index_count % 3 > 0:
                raise Exception(
                    f'[SKN.read()]: Bad indices data: {index_count}')

            # read indices by face
            face_count = index_count // 3
            for i in range(face_count):
                face = bs.read_uint16(3)
                # check dupe index in a face
                if not (face[0] == face[1] or face[1] == face[2] or face[2] == face[0]):
                    self.indices.extend(face)

            # read vertices
            self.vertices = [SKNVertex() for i in range(vertex_count)]
            for i in range(vertex_count):
                vertex = self.vertices[i]
                vertex.position = bs.read_vec3()
                vertex.influences = bs.read_bytes(4)
                vertex.weights = bs.read_float(4)
                bs.pad(12)  # pad normal
                vertex.uv = bs.read_vec2()
                # 0: basic, 1: color, 2: tangent
                if vertex_type >= 1:
                    # pad 4 byte color
                    bs.pad(4)
                    if vertex_type == 2:
                        # pad vec4 tangent
                        bs.pad(16)


class SO:
    def __init__(self):
        self.name = None
        self.central = None

        # for sco only
        self.pivot = None

        # assume sco/scb only have 1 material
        self.material = None
        self.indices = []
        # important: uv can be different at each index, can not map this uv data by vertex
        self.uvs = []
        # not actual vertex, its a position of vertex, no reason to create a class
        self.vertices = []

        # for scb only
        # 1 - vertex color
        # 2 - local origin locator and pivot
        self.scb_flag = 2

    def read_sco(self, path):
        with open(path, 'r') as f:
            lines = f.readlines()
            lines = [line[:-1] for line in lines]

            magic = lines[0]
            if magic != '[ObjectBegin]':
                raise Exception(
                    f'[SO.read_sco()]: Wrong file signature: {magic}')

            index = 1  # skip magic
            len1234 = len(lines)
            while index < len1234:
                inp = lines[index].split()
                if len(inp) == 0:  # cant split, definitely not voldemort
                    index += 1
                    continue

                if inp[0] == 'CentralPoint=':
                    self.central = Vector(
                        float(inp[1]), float(inp[2]), float(inp[3]))

                elif inp[0] == 'PivotPoint=':
                    self.pivot = Vector(
                        float(inp[1]), float(inp[2]), float(inp[3]))

                elif inp[0] == 'Verts=':
                    vertex_count = int(inp[1])
                    for i in range(index+1, index+1 + vertex_count):
                        inp2 = lines[i].split()
                        self.vertices.append(Vector(
                            float(inp2[0]), float(inp2[1]), float(inp2[2])))
                    index = i+1
                    continue

                elif inp[0] == 'Faces=':
                    face_count = int(inp[1])
                    for i in range(index+1, index+1 + face_count):
                        inp2 = lines[i].replace('\t', ' ').split()

                        # skip bad faces
                        face = (int(inp2[1]), int(inp2[2]), int(inp2[3]))
                        if face[0] == face[1] or face[1] == face[2] or face[2] == face[0]:
                            continue
                        self.indices.extend(face)

                        self.material = inp2[4]

                        # u v, u v, u v
                        self.uvs.append(
                            Vector(float(inp2[5]), float(inp2[6])))
                        self.uvs.append(
                            Vector(float(inp2[7]), float(inp2[8])))
                        self.uvs.append(
                            Vector(float(inp2[9]), float(inp2[10])))

                    index = i+1
                    continue

                index += 1

    def read_scb(self, path):
        with open(path, 'rb') as f:
            bs = BinaryStream(f)

            magic = bs.read_ascii(8)
            if magic != 'r3d2Mesh':
                raise Exception(
                    f'[SO.read_scb()]: Wrong file signature: {magic}')

            major, minor = bs.read_uint16(2)
            if major not in (3, 2) and minor != 1:
                raise Exception(
                    f'[SO.read_scb()]: Unsupported file version: {major}.{minor}')

            bs.pad(128)

            vertex_count, face_count, self.scb_flag = bs.read_uint32(3)

            # bouding box
            bs.pad(24)

            vertex_type = 0  # for padding colors later
            if major == 3 and minor == 2:
                vertex_type = bs.read_uint32()

            self.vertices = bs.read_vec3(vertex_count)

            if vertex_type == 1:
                bs.pad(4 * vertex_count)  # pad all vertex colors

            self.central = bs.read_vec3()
            # no pivot in scb

            for i in range(face_count):
                face = bs.read_uint32(3)
                if face[0] == face[1] or face[1] == face[2] or face[2] == face[0]:
                    continue
                self.indices.extend(face)

                self.material = bs.read_padded_ascii(64)

                uvs = bs.read_float(6)

                # u u u, v v v
                self.uvs.append(Vector(uvs[0], uvs[3]))
                self.uvs.append(Vector(uvs[1], uvs[4]))
                self.uvs.append(Vector(uvs[2], uvs[5]))


def process_skn(path):
    d = dirname(path)
    base = basename(path).replace('.skn', '')
    uvee_dir = d+f'/uvee_{base}'
    if not exists(uvee_dir):
        mkdir(uvee_dir)
    skn = SKN()
    skn.read(path)
    for submesh in skn.submeshes:
        img = Image.new('RGBA', (1024, 1024))
        draw = ImageDraw.Draw(img)

        vertices = skn.vertices[submesh.vertex_start:
                                submesh.vertex_start+submesh.vertex_count]
        indices = skn.indices[submesh.index_start:submesh.index_start +
                              submesh.index_count]

        index_count = len(indices)
        face_count = index_count // 3
        min_index = min(indices)
        for i in range(0, index_count):
            indices[i] -= min_index

        for i in range(0, face_count):
            vertex1 = vertices[indices[i*3]]
            vertex2 = vertices[indices[i*3+1]]
            vertex3 = vertices[indices[i*3+2]]
            draw.line((1024 * vertex1.uv.x, 1024 * vertex1.uv.y, 1024 *
                      vertex2.uv.x, 1024 * vertex2.uv.y), fill=0xFFFFFFFF)
            draw.line((1024 * vertex2.uv.x, 1024 * vertex2.uv.y, 1024 *
                      vertex3.uv.x, 1024 * vertex3.uv.y), fill=0xFFFFFFFF)
            draw.line((1024 * vertex3.uv.x, 1024 * vertex3.uv.y, 1024 *
                      vertex1.uv.x, 1024 * vertex1.uv.y), fill=0xFFFFFFFF)
        img_path = uvee_dir + f'/{submesh.name}.png'
        img_path = img_path.replace('\\', '/')
        img.save(img_path)
        print(f'Done: {img_path}')


def process_so(path):
    d = dirname(path)
    base = basename(path).replace('.sco', '').replace('.scb', '')

    so = SO()
    if path.endswith('.sco'):
        so.read_sco(path)
    else:
        so.read_scb(path)

    img = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(img)

    uvs = so.uvs

    index_count = len(uvs)
    face_count = index_count // 3

    for i in range(0, face_count):
        uv1 = uvs[i*3]
        uv2 = uvs[i*3+1]
        uv3 = uvs[i*3+2]
        draw.line((1024 * uv1.x, 1024 * uv1.y, 1024 *
                  uv2.x, 1024 * uv2.y), fill=0xFFFFFFFF)
        draw.line((1024 * uv2.x, 1024 * uv2.y, 1024 *
                  uv3.x, 1024 * uv3.y), fill=0xFFFFFFFF)
        draw.line((1024 * uv3.x, 1024 * uv3.y, 1024 *
                  uv1.x, 1024 * uv1.y), fill=0xFFFFFFFF)

    img_path = d + f'/uvee_{base}.png'
    img_path = img_path.replace('\\', '/')
    img.save(img_path)
    print(f'Done: {img_path}')


def process(path):
    if path.endswith('.skn'):
        try:
            process_skn(path)
        except Exception as e:
            print(f'Failed to read: {path}')
            print(e)
    elif path.endswith('.scb') or path.endswith('.sco'):
        try:
            process_so(path)
        except Exception as e:
            print(f'Failed to read: {path}')
            print(e)


argv = argv[1:]
if len(argv) == 0:
    print('Drop skn, sco, scb files into this program.')
else:
    for path in argv:
        if isdir(path):
            for root, dirs, files in walk(path):
                for f in files:
                    process(root+'/'+f)
        else:
            process(path)


input('Enter to exit.')
