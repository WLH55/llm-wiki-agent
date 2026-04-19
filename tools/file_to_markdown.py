import argparse
from tqdm import tqdm
from pathlib import Path
from markitdown import MarkItDown


def convert_directory_to_md(input_dir: Path, delete_source: bool = False):
    """
    将目录中的所有文件转换为 Markdown 格式。可选择删除原始文件。
    :param input_dir: str
        指向待处理目录的 Path 对象。
    :param delete_source: bool = False
        是否删除原始源文件。默认为 False。
    """

    md = MarkItDown(enable_plugins=False)

    # 获取待转换的文件列表
    files_to_process = [f for f in input_dir.rglob('*') if f.is_file()]

    if not files_to_process:
        print(f"在 {input_dir} 中未找到文件！")
        return

    for file_path in tqdm(files_to_process, desc="正在转换文件"):
        # 跳过隐藏文件和已有的 markdown 文件
        if file_path.name.startswith('.') or file_path.suffix.lower() == '.md':
            print(f"跳过转换：{file_path.name}")
            continue

        # 将文件路径转换为 .md
        output_path = file_path.with_suffix(".md")
        try:
            # 执行转换
            result = md.convert(str(file_path))
            # 保存为 .md 文件
            output_path.write_text(result.text_content, encoding="utf-8")
            # 可选：删除原始文件
            if delete_source:
                file_path.unlink()
            tqdm.write(f"已转换：{file_path.name}")
        except Exception as e:
            tqdm.write(f"失败：无法转换 '{file_path.name}'。原因：{e}")


def main(args):
    # 设置路径
    input_path = Path(args.input_dir).resolve()
    print("-" * 40)
    print(f"输入目录：{input_path}")
    print("-" * 40)

    # 执行转换
    try:
        convert_directory_to_md(input_path, args.delete_source)
        print("\n转换过程完成。")
    except FileNotFoundError:
        print(f"\n错误：未找到输入目录 {input_path}")
    except Exception as e:
        print(f"\n执行过程中发生意外错误：{e}")


if __name__ == "__main__":
    """命令行参数解析。"""
    parser = argparse.ArgumentParser(description="将目录中的所有文件转换为 Markdown 格式，可选择删除原始文件。")
    parser.add_argument(
        "--input_dir",
        type=str,
        help="包含待转换文件的目录路径。"
    )
    parser.add_argument(
        "--delete_source",
        action="store_true",
        help="是否删除原始源文件。"
    )
    args = parser.parse_args()

    main(args)
