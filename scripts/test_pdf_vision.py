"""
미래에셋 증권 AI 데일리 글로벌 마켓 브리핑 PDF → OpenAI Vision API 텍스트 추출 테스트.

Usage:
    .venv/bin/python scripts/test_pdf_vision.py <pdf_url_or_path>
"""
import sys
import base64
import tempfile
from pathlib import Path

import requests
from pdf2image import convert_from_path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """당신은 미래에셋증권 'AI 데일리 글로벌 마켓 브리핑' PDF를 구조화된 텍스트로 변환하는 전문가입니다.

아래 형식으로 정확히 추출해주세요:

## 제목
(보고서 제목과 부제)

## Summary
(요약 섹션 전문)

## 주요 이벤트
(각 이벤트 제목 + 본문)

## 특징종목
(각 카테고리별 종목 및 수치)

## 채권/외환/상품
(금리, 환율, 원자재 데이터)

규칙:
- 모든 수치(지수, 등락률, 금리, 환율)를 빠짐없이 추출
- 종목명과 등락률을 정확히 매칭
- 원문 그대로 추출 (요약하지 말 것)
"""


def download_pdf(url: str) -> Path:
    """URL에서 PDF 다운로드 → 임시 파일 반환."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(resp.content)
    tmp.close()
    return Path(tmp.name)


def pdf_to_images(pdf_path: Path, dpi: int = 200) -> list[str]:
    """PDF 각 페이지를 base64 PNG로 변환."""
    images = convert_from_path(str(pdf_path), dpi=dpi)
    encoded = []
    for img in images:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        with open(tmp.name, "rb") as f:
            encoded.append(base64.b64encode(f.read()).decode())
    return encoded


def extract_text_via_vision(images_b64: list[str], model: str = "gpt-4o") -> str:
    """OpenAI Vision API로 이미지에서 텍스트 추출."""
    client = OpenAI()

    content = []
    for i, img_b64 in enumerate(images_b64):
        content.append({
            "type": "text",
            "text": f"[페이지 {i+1}/{len(images_b64)}]"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_b64}",
                "detail": "high"
            }
        })

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ],
        max_tokens=4096,
        temperature=0
    )

    return response.choices[0].message.content


def main():
    if len(sys.argv) < 2:
        print("Usage: .venv/bin/python scripts/test_pdf_vision.py <pdf_url_or_path>")
        sys.exit(1)

    source = sys.argv[1]

    # URL or local path
    if source.startswith("http"):
        print(f"PDF 다운로드 중... ", end="", flush=True)
        pdf_path = download_pdf(source)
        print(f"OK ({pdf_path})")
    else:
        pdf_path = Path(source)
        if not pdf_path.exists():
            print(f"파일을 찾을 수 없습니다: {source}")
            sys.exit(1)

    # PDF → images
    print(f"PDF → 이미지 변환 중 (dpi=200)... ", end="", flush=True)
    images = pdf_to_images(pdf_path)
    print(f"OK ({len(images)} 페이지)")

    # Vision API
    print(f"OpenAI Vision API 호출 중 (gpt-4o)... ", end="", flush=True)
    text = extract_text_via_vision(images)
    print("OK")

    print("\n" + "=" * 80)
    print("추출 결과")
    print("=" * 80)
    print(text)

    # 결과 저장
    output_path = Path("logs/test_pdf_vision_output.txt")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"\n결과 저장: {output_path}")


if __name__ == "__main__":
    main()
