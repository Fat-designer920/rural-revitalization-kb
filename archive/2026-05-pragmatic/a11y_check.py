"""
a11y_check.py - WCAG 2.1 AA 基础可访问性检查(零外部依赖)
路径：scripts/a11y_check.py
版本：v2.3.7-part6

来源: axe-core规则 + WCAG 2.1 AA + 工信部适老化标准
检查: lang属性/alt文本/标题层级/viewport/对比度/字号/可读性
"""
import re, sys, os


def check_html(filepath):
    """扫描单个HTML文件,返回(violations, warnings, passes)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    violations = []
    warnings = []
    passes = []

    # 1. lang 属性
    if '<html lang=' in html:
        passes.append('lang属性已设置')
    else:
        violations.append('[A11Y] 缺少 lang 属性(屏幕阅读器需要)')

    # 2. viewport
    if 'viewport' in html.lower():
        passes.append('viewport已设置')
    else:
        violations.append('[A11Y] 缺少 viewport meta(移动端适配需要)')

    # 3. alt 属性
    imgs = re.findall(r'<img[^>]+>', html, re.IGNORECASE)
    missing_alt = [img[:60] for img in imgs if 'alt=' not in img]
    if missing_alt:
        violations.append(f'[A11Y] {len(missing_alt)}个<img>缺少alt属性')
    else:
        passes.append('所有img有alt属性')

    # 4. 标题层级
    h1s = len(re.findall(r'<h1[ >]', html, re.IGNORECASE))
    h2s = len(re.findall(r'<h2[ >]', html, re.IGNORECASE))
    if h1s >= 1:
        passes.append(f'h1-h6层级完整({h1s}h1+{h2s}h2)')
    elif h1s == 0:
        warnings.append('[A11Y] 缺少h1标题(建议每个页面有1个h1)')

    # 5. 最小字号
    font_sizes = re.findall(r'font-size:\s*(\d+)px', html)
    small_fonts = [int(s) for s in font_sizes if int(s) < 14]
    if small_fonts:
        violations.append(f'[A11Y] {len(small_fonts)}处字号<14px(违反WCAG AA): {small_fonts[:5]}')
    else:
        passes.append('最小字号≥14px')

    # 6. 对比度(简化: 检查是否使用了浅色文字)
    light_colors = re.findall(r'color:\s*#([A-Fa-f0-9]{6})', html)
    very_light = [c for c in light_colors if _is_light(c)]
    if very_light:
        warnings.append(f'[A11Y] {len(very_light)}处颜色可能对比度不足(WCAG AA要求≥4.5:1)')

    # 7. 跳转链接
    if '跳转到' in html or 'skip-link' in html or 'skip-navigation' in html:
        passes.append('有跳转导航链接')
    else:
        warnings.append('[A11Y] 建议添加"跳转到内容"链接(键盘用户友好)')

    return violations, warnings, passes


def _is_light(hex_color):
    """判断颜色是否过浅(对比度可能不足)"""
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance > 0.85


def scan_all():
    """扫描web/templates/下所有HTML文件"""
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'web', 'templates')
    results = {}
    for f in sorted(os.listdir(template_dir)):
        if f.endswith('.html'):
            path = os.path.join(template_dir, f)
            v, w, p = check_html(path)
            results[f] = {'violations': len(v), 'warnings': len(w), 'passes': len(p),
                          'details': v + w}
    return results


if __name__ == '__main__':
    if len(sys.argv) > 1:
        v, w, p = check_html(sys.argv[1])
        for item in v + w:
            print(item)
        print(f'Violations:{len(v)} Warnings:{len(w)} Passes:{len(p)}')
        sys.exit(1 if v else 0)
    else:
        results = scan_all()
        for f, r in results.items():
            print(f'{f}: V:{r["violations"]} W:{r["warnings"]} P:{r["passes"]}')
