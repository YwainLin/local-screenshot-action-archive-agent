"""生成脱敏测试截图样例

运行方式：python -m tests.fixtures.generate_test_images
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_test_image(
    path: Path,
    text: str,
    size: tuple[int, int] = (400, 300),
    bg_color: str = "white",
    text_color: str = "black",
) -> None:
    """创建带文字的测试图片"""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()

    draw.text((20, 20), text, fill=text_color, font=font)
    img.save(path, quality=95)


def generate_all_fixtures(output_dir: Path) -> None:
    """生成所有测试样例"""
    fixtures_dir = output_dir / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 完全相同的文件
    identical_content = "Same content for identical test"
    create_test_image(fixtures_dir / "identical_a.png", identical_content)
    create_test_image(fixtures_dir / "identical_b.png", identical_content)

    # 不同压缩的相同内容
    create_test_image(fixtures_dir / "compressed_original.png", "Compressed content")
    img = Image.open(fixtures_dir / "compressed_original.png")
    img.save(fixtures_dir / "compressed_low.jpg", quality=30)
    img.save(fixtures_dir / "compressed_high.jpg", quality=95)

    # 近似但不应合并的图片
    create_test_image(
        fixtures_dir / "similar_a.png",
        "Similar but different content A",
        bg_color="lightblue",
    )
    create_test_image(
        fixtures_dir / "similar_b.png",
        "Similar but different content B",
        bg_color="lightblue",
    )

    # 中文 OCR 测试
    create_test_image(
        fixtures_dir / "chinese_ocr.png",
        "订单已发货\n预计8月5日送达\n快递单号：SF1234567890",
    )

    # 英文 OCR 测试
    create_test_image(
        fixtures_dir / "english_ocr.png",
        "Meeting scheduled for\nSeptember 15, 2026\nDeadline: Submit report",
    )

    # 低清晰度测试
    img_low = Image.new("RGB", (100, 100), color="gray")
    img_low.save(fixtures_dir / "low_resolution.png")

    # 空白图测试
    img_blank = Image.new("RGB", (400, 300), color="white")
    img_blank.save(fixtures_dir / "blank_image.png")

    # 含日期行动词的模拟通知
    create_test_image(
        fixtures_dir / "notification_with_date.png",
        "课程通知\n截止日期：2026年8月20日\n请尽快预约",
    )

    # 含疑似敏感数字的模拟图片
    create_test_image(
        fixtures_dir / "sensitive_numbers.png",
        "银行卡号：6222 0200 0012 3456 789\n验证码：123456",
    )

    print(f"测试样例已生成到：{fixtures_dir}")
    print(f"生成文件列表：")
    for f in sorted(fixtures_dir.iterdir()):
        print(f"  - {f.name}")


if __name__ == "__main__":
    test_dir = Path(__file__).parent
    generate_all_fixtures(test_dir)
