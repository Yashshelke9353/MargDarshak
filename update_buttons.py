import re

file_path = r'c:\Users\yshel\anaconda_projects\Pictures\Dream Project\marg-darshak-main\templates\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

def repl(m):
    url = m.group(1)
    # Extract the raw text of the link by stripping any HTML tags inside (e.g. <i> )
    text_content = re.sub(r'<[^>]*>', '', m.group(2)).strip()
    
    return f'''<a href="{url}" class="feature-access-btn" data-tilt data-tilt-max="15" data-tilt-scale="1.05">
                            <div class="feat-btn-inner">
                                <img src="/static/icon-192.png" alt="Logo">
                                <span>{text_content}</span>
                                <i class="fas fa-arrow-right"></i>
                            </div>
                        </a>'''

# Regex matches <a ... class="btn-premium" ...>...</a> and <a ... class="feat-btn" ...>...</a>
new_content = re.sub(r'<a href="([^"]+)" (?:class|style)="[^>]*class="[^"]*(?:feat-btn|btn-premium)[^"]*"[^>]*>(.*?)</a>', repl, content)
new_content = re.sub(r'<a href="([^"]+)" class="[^"]*(?:feat-btn|btn-premium)[^"]*"[^>]*>(.*?)</a>', repl, new_content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done via scratch script")
