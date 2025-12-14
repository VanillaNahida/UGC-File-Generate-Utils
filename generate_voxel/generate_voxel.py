#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON数据转方块生成器
从JSON文件读取坐标和颜色数据，生成对应的3D方块实体
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../proto_gen"))

import json
from typing import List

from model.block_model import BlockModel
from assembler.block_assembler import BlockAssembler
from helper.file_helper import FileHelper
from helper.block_helper import BlockHelper
from config.block_config import BlockTemplate, BlockConfig


class Config:
    GLOBAL_SCALE = 0.01  # 全局缩放

    # 起始位置
    START_POSITION = {
        'x': 0.0,
        'y': 0.0,
        'z': 0.0
    }

    # 实体ID起始值
    ENTITY_ID_START = 1078000000

    # 输入文件路径
    input_file = "../output/model_voxels.json"

    # 导出gia文件
    output_file = "../output/voxel_model.gia"


def json_to_block_data(json_block: dict, templates: List[BlockTemplate]) -> BlockModel:
    """
    将JSON方块数据转换为BlockData

    Args:
        json_block: JSON数据，包含 x, y, z, color
        templates: 可用模板列表

    Returns:
        BlockData: 方块数据对象
    """
    # 提取坐标和颜色
    x = int(json_block['x'])
    y = int(json_block['y'])
    z = int(json_block['z'])
    color = json_block['color']

    # 找到最匹配的模板模板
    template = BlockHelper.find_closest_template(color, templates)

    # 计算缩放
    scale_x, scale_y, scale_z = BlockHelper.calculate_scale(template, Config.GLOBAL_SCALE)

    # 计算位置
    position_x, position_y, position_z = BlockHelper.calculate_position(x, y, z, Config.GLOBAL_SCALE,
                                                                        Config.START_POSITION['x'],
                                                                        Config.START_POSITION['y'],
                                                                        Config.START_POSITION['z'])

    # 创建BlockModel
    block_data = BlockModel(
        template_id=template.template_id,
        name=f"Block_{x}_{y}_{z}",

        position_x=position_x,
        position_y=position_y,
        position_z=position_z,
        scale_x=scale_x,
        scale_y=scale_y,
        scale_z=scale_z
    )

    return block_data


def load_json_file(filepath: str) -> List[dict]:
    """
    加载JSON文件

    Args:
        filepath: JSON文件路径

    Returns:
        List[dict]: 方块数据列表
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    else:
        raise ValueError("JSON格式不支持，应为数组")


def main():
    print("=" * 70)
    print("JSON数据转方块生成器")
    print("=" * 70)
    print()

    # 显示配置
    print("当前配置:")
    print(f"  可用模板数量: {len(BlockConfig.AVAILABLE_BLOCKS)}")
    print(f"  全局缩放系数: {Config.GLOBAL_SCALE}")
    print(f"  起始位置: X={Config.START_POSITION['x']}, "
          f"Y={Config.START_POSITION['y']}, "
          f"Z={Config.START_POSITION['z']}")
    print()

    print("读取JSON文件...")
    try:
        json_blocks = load_json_file(Config.input_file)
        print(f"读取到 {len(json_blocks)} 个方块数据")
    except FileNotFoundError:
        print(f"Error: 文件不存在: {Config.input_file}")
        return
    except Exception as e:
        print(f"Error: 读取文件失败: {e}")
        return
    print()

    print("转换为方块数据...")
    blocks = []
    color_stats = {}  # 统计每种模板使用次数

    for i, json_block in enumerate(json_blocks):
        block_data = json_to_block_data(
            json_block,
            BlockConfig.AVAILABLE_BLOCKS
        )
        blocks.append(block_data)

        # 统计
        template_id = block_data.template_id
        color_stats[template_id] = color_stats.get(template_id, 0) + 1

    print(f"共转换 {len(blocks)} 个方块")
    print()

    print("方块使用统计:")
    for template_id, count in color_stats.items():
        # 找到对应的模板
        template = next((t for t in BlockConfig.AVAILABLE_BLOCKS if t.template_id == template_id), None)
        if template:
            rgb = template.color_tuple
            print(f"  模板 {template_id} (RGB{rgb}): {count} 个")
    print()

    print("组装Proto...")
    assembler = BlockAssembler(entity_id_start=Config.ENTITY_ID_START)
    proto_data = assembler.assemble(blocks)
    print(f"Protobuf数据大小: {len(proto_data)} 字节")
    print()

    success = FileHelper.save(proto_data, Config.output_file)

    if success:
        print()
        print("=" * 70)
        print("生成完成！")
        print("=" * 70)
        print(f"输入文件: {Config.input_file}")
        print(f"输出文件: {Config.output_file}")
        print(f"方块数量: {len(blocks)}")
        print(f"实体ID范围: {Config.ENTITY_ID_START} - "
              f"{assembler.current_entity_id - 1}")
        print(f"全局缩放: {Config.GLOBAL_SCALE}")
        print()
    else:
        print("Error: 保存失败")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("Error: 程序被用户中断")
    except Exception as e:
        print()
        print(f"Error: {e}")

        import traceback
        traceback.print_exc()
