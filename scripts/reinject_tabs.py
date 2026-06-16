"""Re-inject sibling tab files (_story, _cs, _pm, etc.) into main HTML."""
import re, sys, os

def replace_tab(html, tab_id, new_content):
    pattern = rf'(<div id="tab-{tab_id}" class="tab-panel(?:\s+active)?">\s*\n).*?(\n</div><!-- /tab-{tab_id} -->)'
    return re.sub(pattern, rf'\g<1>{new_content}\n\g<2>', html, flags=re.DOTALL)

date = sys.argv[1] if len(sys.argv) > 1 else None
if not date:
    print("Usage: reinject_tabs.py YYYY-MM-DD"); sys.exit(1)

ym = date[:7]
base = f"output/summary/{ym}/{date}"
main_path = f"{base}.html"

siblings = {
    "story": f"{base}_story.html",
    "cs":    f"{base}_cs.html",
    "pm":    f"{base}_pm.html",
    "stocks": f"{base}_stocks.html",
    "macro":  f"{base}_macro.html",
    "sources": f"{base}_sources.html",
}

with open(main_path, encoding="utf-8") as f:
    html = f.read()

for tab_id, sib_path in siblings.items():
    if os.path.exists(sib_path):
        with open(sib_path, encoding="utf-8") as f:
            content = f.read().strip()
        html = replace_tab(html, tab_id, content)
        print(f"  Injected: {tab_id}")

with open(main_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Done: {main_path}")
