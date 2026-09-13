import markdown
import bleach
from bs4 import BeautifulSoup


def render_markdown_safe(markdown_text: str) -> str:
    """Render markdown to HTML with safe sanitization."""
    if not markdown_text:
        return ""
    
    # Convert markdown to HTML
    html = markdown.markdown(
        markdown_text,
        extensions=[
            "fenced_code",
            "tables",
            "nl2br",
            "sane_lists",
        ]
    )
    
    # Sanitize HTML
    allowed_tags = [
        "p", "br", "strong", "em", "u", "code", "pre", "blockquote",
        "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "thead", "tbody", "tr", "th", "td", "a", "img",
        "hr", "del", "ins", "sub", "sup", "mark",
    ]
    
    allowed_attributes = {
        "a": ["href", "title", "target", "rel"],
        "img": ["src", "alt", "title", "width", "height"],
        "code": ["class"],
        "pre": ["class"],
        "th": ["scope"],
        "td": ["colspan", "rowspan"],
        "div": ["class"],
        "span": ["class"],
    }
    
    allowed_protocols = ["http", "https", "mailto"]
    
    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=True,
    )
    
    # Add target="_blank" and rel="noopener noreferrer" to external links
    soup = BeautifulSoup(clean_html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith(("http://", "https://")):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    
    return str(soup)


def render_markdown_to_text(markdown_text: str, max_length: int = 500) -> str:
    """Render markdown to plain text for summaries."""
    if not markdown_text:
        return ""
    
    html = markdown.markdown(markdown_text)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."
    
    return text