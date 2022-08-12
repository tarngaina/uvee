from struct import pack, unpack

class MVector():
    def __init__(self, x, y, z=None):
        self.x = x
        self.y = y
        self.z = z

class BinaryStream:
    def __init__(self, f):
        self.stream = f

    def seek(self, pos, mode=0):
        self.stream.seek(pos, mode)

    def tell(self):
        return self.stream.tell()

    def pad(self, length):
        self.stream.seek(length, 1)

    def read_byte(self):
        return self.stream.read(1)

    def read_bytes(self, length):
        return self.stream.read(length)

    def read_bool(self):
        return unpack('?', self.stream.read(1))[0]

    def read_int16(self):
        return unpack('h', self.stream.read(2))[0]

    def read_uint16(self):
        return unpack('H', self.stream.read(2))[0]

    def read_int32(self):
        return unpack('i', self.stream.read(4))[0]

    def read_uint32(self):
        return unpack('I', self.stream.read(4))[0]

    def read_float(self):
        return unpack('f', self.stream.read(4))[0]

    def read_char(self):
        return unpack('b', self.stream.read(1))[0]

    def read_zero_terminated_string(self):
        res = ''
        while True:
            c = self.read_char()
            if c == 0:
                break
            res += chr(c)
        return res

    def read_padded_string(self, length):
        return bytes(filter(lambda b: b != 0, self.stream.read(length))).decode('ascii')

    def read_vec2(self):
        return MVector(self.read_float(), self.read_float())

    def read_vec3(self):
        return MVector(self.read_float(), self.read_float(), self.read_float())

    def write_bytes(self, value):
        self.stream.write(value)

    def write_int16(self, value):
        self.write_bytes(pack('h', value))

    def write_uint16(self, value):
        self.write_bytes(pack('H', value))

    def write_int32(self, value):
        self.write_bytes(pack('i', value))

    def write_uint32(self, value):
        self.write_bytes(pack('I', value))

    def write_float(self, value):
        self.write_bytes(pack('f', value))

    def write_padded_string(self, length, value):
        while len(value) < length:
            value += '\u0000'
        self.write_bytes(value.encode('ascii'))

    def write_vec2(self, vec2):
        self.write_float(vec2.x)
        self.write_float(vec2.y)

    def write_vec3(self, vec3):
        self.write_float(vec3.x)
        self.write_float(vec3.y)
        self.write_float(vec3.z)


class SKNVertex:
    def __init__(self):
        self.position = None
        self.influences = None
        self.weights = None
        self.normal = None
        self.uv = None

        # for dumping
        self.uv_index = None
        self.new_index = None


class SKNSubmesh:
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

        # for loading
        self.name = None
        
    def read(self, path):
        with open(path, 'rb') as f:
            bs = BinaryStream(f)

            magic = bs.read_uint32()
            if magic != 0x00112233:
                raise FunnyError(
                    f'[SKN.read()]: Wrong signature file: {magic}')

            major = bs.read_uint16()
            minor = bs.read_uint16()
            if major not in [0, 2, 4] and minor != 1:
                raise FunnyError(
                    f'[SKN.read()]: Unsupported file version: {major}.{minor}')

            self.name = path.split('/')[-1].split('.')[0]
            vertex_type = 0
            if major == 0:
                # version 0 doesn't have submesh data
                index_count = bs.read_uint32()
                vertex_count = bs.read_uint32()

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
                for i in range(0, submesh_count):
                    submesh = SKNSubmesh()
                    submesh.name = bs.read_padded_string(64)
                    submesh.vertex_start = bs.read_uint32()
                    submesh.vertex_count = bs.read_uint32()
                    submesh.index_start = bs.read_uint32()
                    submesh.index_count = bs.read_uint32()
                    self.submeshes.append(submesh)

                if major == 4:
                    bs.pad(4)  # flags

                index_count = bs.read_uint32()
                vertex_count = bs.read_uint32()

                # junk stuff from version 4
                if major == 4:  # pad all this, cause we dont need?
                    bs.pad(4)  # vertex size
                    vertex_type = bs.read_uint32()
                    bs.pad(24)  # bouding box: 2 vec3 min-max
                    # bouding sphere: vec3 central + float radius
                    bs.pad(12 + 4)

            if index_count % 3 > 0:
                raise FunnyError(
                    f'[SKN.read()]: Bad indices data: {index_count}')

            # read indices by face
            face_count = index_count // 3
            for i in range(0, face_count):
                face = (bs.read_uint16(), bs.read_uint16(),
                        bs.read_uint16())
                # check dupe index in a face
                if not (face[0] == face[1] or face[1] == face[2] or face[2] == face[0]):
                    self.indices += face

            # read vertices
            for i in range(0, vertex_count):
                vertex = SKNVertex()
                vertex.position = bs.read_vec3()
                vertex.influences = [
                    bs.read_byte(), bs.read_byte(), bs.read_byte(), bs.read_byte()]
                vertex.weights = [
                    bs.read_float(), bs.read_float(), bs.read_float(), bs.read_float()]
                vertex.normal = bs.read_vec3()
                vertex.uv = bs.read_vec2()
                # 0: basic, 1: color, 2: color and tangent
                if vertex_type >= 1:
                    # pad 4 byte color
                    bs.pad(4)
                    if vertex_type == 2:
                        # pad vec4 tangent
                        bs.pad(16)
                self.vertices.append(vertex)


from PIL import Image, ImageDraw
from sys import argv
from os.path import basename, dirname, exists
from os import mkdir


def process(path):
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

        vertices = skn.vertices[submesh.vertex_start:submesh.vertex_start+submesh.vertex_count]
        indices = skn.indices[submesh.index_start:submesh.index_start+submesh.index_count]
        
        index_count = len(indices)
        face_count = index_count // 3
        min_index = min(indices)
        for i in range(0, index_count):
            indices[i] -= min_index

        for i in range(0, face_count):
            vertex1 = vertices[indices[i*3]]
            vertex2 = vertices[indices[i*3+1]]
            vertex3 = vertices[indices[i*3+2]]
            draw.line((1024 * vertex1.uv.x, 1024 * vertex1.uv.y, 1024 * vertex2.uv.x, 1024 * vertex2.uv.y), fill = 0xFFFFFFFF)
            draw.line((1024 * vertex2.uv.x, 1024 * vertex2.uv.y, 1024 * vertex3.uv.x, 1024 * vertex3.uv.y), fill = 0xFFFFFFFF)
            draw.line((1024 * vertex3.uv.x, 1024 * vertex3.uv.y, 1024 * vertex1.uv.x, 1024 * vertex1.uv.y), fill = 0xFFFFFFFF)
        img_path = uvee_dir + f'/{submesh.name}.png'
        img_path.replace('\\', '/')
        img.save(img_path)
        print(f'Done: {img_path}')


argv = argv[1:]
if len(argv) == 0:
    print('Drop skn file into this program.')
else:
    for path in argv:
        if path.endswith('.skn'):
            try:
                process(path)
            except Exception as e:
                print(f'Failed to read: {path}')
                print(e)

input('Enter to exit.')
