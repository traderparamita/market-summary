#!/usr/local/bin/python3.12
"""
HTML → PDF 변환기 (Playwright headless Chromium)

Chart.js·Spoqa Han Sans·CSS Grid 등을 모두 살리기 위해 Chromium 렌더링을 사용한다.

사용:
  .venv/bin/python scripts/html_to_pdf.py output/weekly-pm/2026-05-01.html
  .venv/bin/python scripts/html_to_pdf.py output/weekly-pm/2026-05-01.html --tab pm
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path


async def render_pdf(html_path: str, pdf_path: str, *, tab: str | None = None,
                     exclude: list[str] | None = None,
                     wait_ms: int = 1500) -> None:
    from playwright.async_api import async_playwright

    exclude = exclude or []
    file_url = Path(html_path).resolve().as_uri()
    if tab:
        file_url += f"#{tab}"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1360, "height": 900})
        page = await context.new_page()
        await page.goto(file_url, wait_until="networkidle")

        # 특정 탭만 PDF 로 뽑고 싶을 때: 해당 탭 활성화 후 다른 탭 숨김
        if tab:
            await page.evaluate(
                """(tabId) => {
                  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                  const panel = document.getElementById('tab-' + tabId);
                  if (panel) panel.classList.add('active');
                  document.querySelectorAll('.tab-bar').forEach(b => b.style.display = 'none');
                }""",
                tab,
            )

        # Chart.js 애니메이션 + 폰트 로드 대기
        await page.wait_for_timeout(wait_ms)
        await page.evaluate("document.fonts.ready")

        # 모든 탭을 한 PDF 로 뽑고 싶다면: print CSS 로 모든 panel 보이게
        if not tab:
            # 1) 빈 탭(placeholder/공백 only) 자동 마킹 + 마지막 가시 탭 표시
            await page.evaluate("""
                () => {
                  document.querySelectorAll('.tab-panel').forEach(p => {
                    const stripped = p.innerHTML
                      .replace(/<!--[\\s\\S]*?-->/g, '')
                      .replace(/\\s+/g, '');
                    if (stripped.length < 20) p.setAttribute('data-empty','true');
                  });
                  // 가시 탭 중 마지막 → page-break-after 해제
                  const visible = [...document.querySelectorAll('.tab-panel:not([data-empty="true"])')];
                  if (visible.length) {
                    const last = visible[visible.length - 1];
                    last.setAttribute('data-last-visible','true');
                    // 면책고지·푸터를 마지막 탭 안으로 이동 (단독 페이지 방지)
                    const disclaimer = document.querySelector('.ai-disclaimer');
                    const footer = document.querySelector('.footer');
                    if (disclaimer) last.appendChild(disclaimer);
                    if (footer) last.appendChild(footer);
                  }
                }
            """)

            exclude_css = "\n".join(
                f"#tab-{t} {{ display: none !important; }}" for t in exclude
            )
            await page.add_style_tag(content=f"""
                /* 모든 탭을 펼쳐서 인쇄 + 빈 탭 자동 숨김 */
                .tab-panel {{ display: block !important; page-break-after: always; }}
                .tab-panel[data-empty="true"] {{ display: none !important; }}
                .tab-panel[data-last-visible="true"] {{ page-break-after: auto !important; }}
                .tab-bar {{ display: none !important; }}
                .back-link {{ display: none !important; }}
                {exclude_css}

                /* 카드·작은 박스만 보호 — 표/섹션 컨테이너는 자유 흐름 (빈 공간 최소화) */
                .pm-hero, .pm-section,
                .story-hero, .cs-hero, .insight-card, .cause-node,
                .session-block, .macro-card, .risk-section, .risk-item,
                .chart-card, .movers-card, .kpi, .risk-card,
                .scenario-card,
                tr {{
                  page-break-inside: avoid;
                  break-inside: avoid;
                }}

                /* 표·섹션 컨테이너는 페이지 흐름 허용 (rows만 보호) */
                .heatmap-section, .heatmap, table {{
                  page-break-inside: auto;
                  break-inside: auto;
                }}

                /* 표 헤더는 분할 시 다음 페이지에 반복 */
                thead {{ display: table-header-group; }}

                /* grid 컨테이너는 자연스럽게 페이지 흐름 허용 (하단 빈공간 최소화) */
                .pm-grid, .chart-grid, .movers-row, .risk-strip,
                .insight-grid, .session-grid, .scenario-grid,
                .risk-items {{
                  break-inside: auto;
                  page-break-inside: auto;
                }}

                /* 차트 높이 인쇄용으로 컴팩트화 */
                .chart-box {{ height: 200px !important; }}
                .chart-card {{ padding: 12px !important; }}

                /* 헤더는 첫 페이지에만 임팩트 */
                .header {{ break-after: avoid; }}

                /* ── 가독성 향상 (PDF 인쇄 전용) ────────────────────────── */

                /* 본문 base 살짝 키움 */
                body {{ font-size: 14px !important; line-height: 1.7 !important; }}

                /* PM Hero — 핵심 메시지 잘 보이게 */
                .pm-hero {{ padding: 22px 26px !important; margin-bottom: 18px !important; }}
                .pm-hero h2 {{ font-size: 14px !important; margin-bottom: 12px !important; }}
                .pm-hero p {{ font-size: 14.5px !important; line-height: 1.95 !important; }}

                /* PM Section — 6 섹션 한국·매크로·... */
                .pm-section {{ padding: 18px 22px !important; margin-bottom: 12px !important; }}
                .pm-section h3 {{ font-size: 16px !important; margin-bottom: 12px !important; padding-bottom: 6px !important; border-bottom: 1px solid var(--border); }}
                .pm-section li {{ font-size: 13.5px !important; line-height: 1.85 !important; margin-bottom: 8px !important; padding-left: 14px !important; }}
                .pm-section li::before {{ font-size: 14px !important; }}

                /* 강조 컬러 강화 (인쇄 시 흐려지지 않게) */
                .hl-up {{ color: #b91c1c !important; font-weight: 700 !important; }}
                .hl-down {{ color: #1e40af !important; font-weight: 700 !important; }}
                .hl-warn {{ color: #c2410c !important; font-weight: 700 !important; }}
                .hl-accent {{ color: #c2410c !important; font-weight: 700 !important; }}
                strong {{ color: #1a1d2e !important; }}

                /* Outlook 박스들 — 가독성 향상 */
                .outlook-divider h2 {{ font-size: 19px !important; margin-bottom: 18px !important; }}
                .outlook-divider h3 {{ font-size: 15px !important; margin-bottom: 14px !important; }}
                .outlook-divider ul {{ font-size: 13px !important; line-height: 1.85 !important; }}
                .outlook-divider ul li {{ margin-bottom: 6px !important; }}

                /* Today Residual / Risk Top 3 박스 */
                [style*="background:#fff8e1"], [style*="background:#fdf2f4"] {{
                  padding: 18px 20px !important;
                }}
                [style*="background:#fff8e1"] ul li,
                [style*="background:#fdf2f4"] ol li {{
                  font-size: 13px !important; line-height: 1.9 !important; margin-bottom: 6px !important;
                }}

                /* Bull/Base/Bear 시나리오 카드 */
                .scenario-card {{ padding: 18px !important; }}
                .scenario-card > div:first-child {{ font-size: 14px !important; margin-bottom: 10px !important; }}
                .scenario-card > div:last-child {{ font-size: 12.5px !important; line-height: 1.8 !important; }}

                /* 캘린더 그리드 박스 */
                .outlook-divider div[style*="grid-template-columns:1fr 1fr"] > div {{
                  padding: 18px !important;
                }}
                .outlook-divider div[style*="grid-template-columns:1fr 1fr"] ul li {{
                  font-size: 12.5px !important; line-height: 1.85 !important; margin-bottom: 5px !important;
                }}
                .outlook-divider div[style*="font-weight:600"] {{ font-size: 14px !important; }}

                /* Positioning 표 */
                table[style*="border-collapse:collapse"] {{ font-size: 13px !important; }}
                table[style*="border-collapse:collapse"] th {{ padding: 10px 8px !important; font-weight: 700 !important; }}
                table[style*="border-collapse:collapse"] td {{ padding: 10px 8px !important; line-height: 1.7 !important; }}

                /* Data Dashboard — KPI 카드 */
                .kpi {{ padding: 14px 18px !important; }}
                .kpi-label {{ font-size: 12px !important; }}
                .kpi-value {{ font-size: 20px !important; }}
                .kpi-chg {{ font-size: 13px !important; }}

                /* Heatmap 표 — 가독성 향상 */
                .heatmap-section h2 {{ font-size: 16px !important; margin-bottom: 10px !important; }}
                .heatmap th {{ font-size: 12px !important; padding: 11px 12px !important; font-weight: 700 !important; }}
                .heatmap td {{ font-size: 13px !important; padding: 9px 12px !important; }}
                .heatmap .name-cell {{ font-size: 13px !important; font-weight: 600 !important; }}
                .heatmap .close-cell {{ font-size: 12.5px !important; }}
                .heatmap .heat-cell {{ font-size: 12.5px !important; font-weight: 700 !important; }}

                /* Risk Dashboard 카드 */
                .risk-card {{ padding: 18px !important; }}
                .risk-card .label {{ font-size: 12.5px !important; }}
                .risk-card .value {{ font-size: 26px !important; }}
                .risk-card .desc {{ font-size: 12px !important; }}

                /* 차트 타이틀 */
                .chart-card .title {{ font-size: 14px !important; margin-bottom: 10px !important; font-weight: 700 !important; }}

                /* 헤더 영역 */
                .header-left h1 {{ font-size: 24px !important; }}
                .header-left .date {{ font-size: 13px !important; }}
                .mood-badge {{ font-size: 13px !important; padding: 8px 16px !important; }}

                /* 푸터·면책고지: 한 줄로 압축, 직전 콘텐츠와 같은 페이지 */
                .ai-disclaimer, .footer {{
                  break-before: avoid !important;
                  page-break-before: avoid !important;
                  break-inside: avoid !important;
                  margin-top: 4px !important;
                  padding: 4px 8px !important;
                  font-size: 8px !important;
                  line-height: 1.3 !important;
                }}
                .ai-disclaimer {{ background: #fafafa !important; }}

                /* tab-panel 의 모든 last-child 체인 보호 (마지막 메모 등) */
                .tab-panel > *:last-child,
                .tab-panel > *:last-child > *:last-child {{
                  break-before: avoid;
                  page-break-before: avoid;
                }}

                @page {{ size: A4; margin: 10mm; }}
            """)
            # 차트가 다시 그려질 시간을 줌
            await page.evaluate("window.dispatchEvent(new Event('resize'))")
            await page.wait_for_timeout(800)

        await page.pdf(
            path=pdf_path,
            format="A4",
            margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            print_background=True,
            prefer_css_page_size=True,
        )
        await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="HTML → PDF (Playwright Chromium)")
    parser.add_argument("html_path", help="입력 HTML 경로")
    parser.add_argument("--out", help="출력 PDF 경로 (기본: 같은 디렉터리, 같은 stem .pdf)")
    parser.add_argument("--tab", help="특정 탭만 (story|pm|cs|data|macro|sources)")
    parser.add_argument("--exclude", help="제외할 탭(쉼표 구분, 예: 'data,sources')")
    parser.add_argument("--wait", type=int, default=1500, help="렌더 대기(ms)")
    args = parser.parse_args()

    html_path = os.path.abspath(args.html_path)
    if not os.path.exists(html_path):
        print(f"[ERROR] HTML not found: {html_path}", file=sys.stderr)
        return 1

    exclude = [t.strip() for t in args.exclude.split(",")] if args.exclude else []

    if args.out:
        pdf_path = os.path.abspath(args.out)
    else:
        stem, _ = os.path.splitext(html_path)
        if args.tab:
            suffix = f"_{args.tab}"
        elif exclude:
            suffix = "_no-" + "-".join(exclude)
        else:
            suffix = ""
        pdf_path = f"{stem}{suffix}.pdf"

    asyncio.run(render_pdf(html_path, pdf_path, tab=args.tab, exclude=exclude,
                           wait_ms=args.wait))
    print(f"[PDF] {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
