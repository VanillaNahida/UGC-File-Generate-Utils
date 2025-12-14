import bpy
import bmesh
import json
import numpy as np
import time

from mathutils import Vector
from mathutils.bvhtree import BVHTree


class Config:
    VOXEL_SIZE = 0.01  # 采样级别
    ALPHA_THRESHOLD = 0.5  # 忽略透明体素阈值
    OUTPUT_PATH = "F:/python/UGC-File-Generate-Utils/model_voxels.json"  # 导出路径


# 纹理缓存管理器
class TextureCache:
    def __init__(self):
        self.cache = {}

    def get_image_data(self, image):
        if image.name in self.cache:
            return self.cache[image.name]

        if image.size[0] == 0 or image.size[1] == 0:
            return None

        # 必须在 object mode 且确保数据已加载
        if not image.pixels:
            image.pixels[:]  # 强制加载

        width = image.size[0]
        height = image.size[1]

        arr = np.array(image.pixels[:], dtype=np.float32)
        arr = arr.reshape((height, width, 4))

        self.cache[image.name] = arr
        return arr

    def sample_color(self, image, uv):
        data = self.get_image_data(image)
        if data is None:
            return 255, 255, 255, 255

        height, width, _ = data.shape

        # UV 坐标处理
        u = uv[0] % 1.0
        v = uv[1] % 1.0

        x = int(u * width)
        y = int(v * height)

        # 防止越界
        x = min(x, width - 1)
        y = min(y, height - 1)

        rgba = data[y, x]
        return int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255), rgba[3]


def hex_color(rgb):
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])


def main():
    start_time = time.time()
    obj = bpy.context.active_object

    if not obj or obj.type != 'MESH':
        print("Error: 请先选中一个网格模型！")
        return

    # 物体模式
    bpy.ops.object.mode_set(mode='OBJECT')

    print(f"开始处理: {obj.name}")

    # 获取评估后的网格
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()

    # 构建 BVH
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bvh = BVHTree.FromBMesh(bm)

    # 准备 UV 层
    uv_layer = bm.loops.layers.uv.verify()

    # 纹理缓存管理器
    tex_cache = TextureCache()

    # 预加载材质对应的图片
    mat_images = {}
    for i, mat in enumerate(mesh.materials):
        if mat and mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    mat_images[i] = node.image
                    break

    voxel_data = {}
    matrix_world = obj.matrix_world

    print("正在体素化...")

    # 用于去重的集合
    processed_keys = set()

    bm.faces.ensure_lookup_table()

    # 只有当三角形面积大于0才处理
    faces = [f for f in bm.faces if f.calc_area() > 0]
    total_faces = len(faces)

    for idx, face in enumerate(faces):
        if idx % 1000 == 0:
            print(f"处理进度: {idx}/{total_faces}")

        img = mat_images.get(face.material_index)

        # 世界坐标顶点
        world_verts = [matrix_world @ v.co for v in face.verts]

        # 计算包围盒
        xs = [v.x for v in world_verts]
        ys = [v.y for v in world_verts]
        zs = [v.z for v in world_verts]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)

        # 确定该面可能触及的体素网格范围
        # 稍微扩大一点范围以确保覆盖边缘
        grid_min_x = int(min_x / Config.VOXEL_SIZE)
        grid_max_x = int(max_x / Config.VOXEL_SIZE)
        grid_min_y = int(min_y / Config.VOXEL_SIZE)
        grid_max_y = int(max_y / Config.VOXEL_SIZE)
        grid_min_z = int(min_z / Config.VOXEL_SIZE)
        grid_max_z = int(max_z / Config.VOXEL_SIZE)

        for x in range(grid_min_x, grid_max_x + 1):
            for y in range(grid_min_y, grid_max_y + 1):
                for z in range(grid_min_z, grid_max_z + 1):

                    key = (x, y, z)
                    if key in processed_keys:
                        continue

                    # 体素中心世界坐标
                    voxel_center = Vector((
                        (x + 0.5) * Config.VOXEL_SIZE,
                        (y + 0.5) * Config.VOXEL_SIZE,
                        (z + 0.5) * Config.VOXEL_SIZE
                    ))

                    # 将体素中心转回局部坐标进行查询
                    local_point = matrix_world.inverted() @ voxel_center

                    # 使用 BVH 查找最近点，限制距离
                    # 只有离网格表面足够近的体素才会被记录
                    # 距离阈值设为体素大小的一半的根号3倍 (立方体对角线的一半)
                    location, normal, index, distance = bvh.find_nearest(local_point)

                    if distance <= (Config.VOXEL_SIZE * 0.866):  # sqrt(3)/2
                        processed_keys.add(key)

                        color_hex = "#FFFFFF"
                        if img:
                            # 使用重心坐标插值获取精确 UV
                            hit_face = bm.faces[index]

                            # 计算重心坐标 P = u*A + v*B + w*C
                            # location 一定在三角形平面上
                            # 需要先计算 location 在 face 上的重心权重

                            p_local = location
                            v1 = hit_face.verts[0].co
                            v2 = hit_face.verts[1].co
                            v3 = hit_face.verts[2].co

                            # 这里的 uv 也是 Vector
                            uv1 = hit_face.loops[0][uv_layer].uv
                            uv2 = hit_face.loops[1][uv_layer].uv
                            uv3 = hit_face.loops[2][uv_layer].uv

                            try:
                                # 计算重心权重
                                bary = bpy.mathutils.geometry.barycentric_transform(
                                    p_local, v1, v2, v3,
                                    Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
                                )
                                # 使用权重插值 UV
                                uv = uv1 * bary.x + uv2 * bary.y + uv3 * bary.z
                            except:
                                # 兜底，回退到第一个点
                                uv = uv1

                            r, g, b, a = tex_cache.sample_color(img, uv)

                            if a < Config.ALPHA_THRESHOLD:
                                continue

                            color_hex = hex_color((r, g, b))

                        # 写入数据
                        voxel_data[key] = {
                            "x": x,
                            "y": z,  # 颠倒YZ轴
                            "z": y,
                            "color": color_hex
                        }

    output_list = list(voxel_data.values())
    with open(Config.OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_list, f, ensure_ascii=False)

    obj_eval.to_mesh_clear()
    bm.free()
    print(f"完成，耗时: {time.time() - start_time:.2f}秒. 生成体素: {len(output_list)}")


if __name__ == "__main__":
    main()
