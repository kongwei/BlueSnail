/* Markdown rendering for BlueSnail WebUI chat messages. */

(function () {
  const ALLOWED_TAGS = new Set([
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
  ]);

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function sanitizeHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    sanitizeNode(template.content);
    return template.innerHTML;
  }

  function sanitizeNode(node) {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.TEXT_NODE) {
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) {
        child.remove();
        continue;
      }
      const tag = child.tagName.toLowerCase();
      if (!ALLOWED_TAGS.has(tag)) {
        const text = document.createTextNode(child.textContent || "");
        child.replaceWith(text);
        continue;
      }
      for (const attr of Array.from(child.attributes)) {
        if (tag === "a" && attr.name === "href") {
          if (!isSafeHref(attr.value)) {
            child.removeAttribute("href");
          }
          continue;
        }
        if (attr.name === "class" && (tag === "pre" || tag === "code")) {
          continue;
        }
        child.removeAttribute(attr.name);
      }
      if (tag === "a" && !child.getAttribute("href")) {
        const text = document.createTextNode(child.textContent || "");
        child.replaceWith(text);
        continue;
      }
      if (tag === "a") {
        child.setAttribute("target", "_blank");
        child.setAttribute("rel", "noopener noreferrer");
      }
      sanitizeNode(child);
    }
  }

  function isSafeHref(href) {
    const value = String(href || "").trim();
    return /^(https?:|mailto:)/i.test(value);
  }

  function renderInline(text) {
    let html = escapeHtml(text);
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    html = html.replace(
      /\[([^\]]+)\]\(([^)\s]+)\)/g,
      (_match, label, url) =>
        isSafeHref(url)
          ? `<a href="${escapeHtml(url)}">${label}</a>`
          : `${label} (${url})`
    );
    return html;
  }

  function renderParagraph(text) {
    return `<p>${renderInline(text).replace(/\n/g, "<br>")}</p>`;
  }

  function renderMarkdown(source) {
    const text = String(source || "").replace(/\r\n/g, "\n");
    if (!text.trim()) {
      return "";
    }

    const parts = text.split(/(```[\s\S]*?```)/g);
    const html = parts
      .map((part) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const body = part.slice(3, -3);
          const firstBreak = body.indexOf("\n");
          const language = firstBreak >= 0 ? body.slice(0, firstBreak).trim() : "";
          const code =
            firstBreak >= 0 ? body.slice(firstBreak + 1) : body;
          const className = language
            ? ` class="language-${escapeHtml(language)}"`
            : "";
          return `<pre><code${className}>${escapeHtml(code.trimEnd())}</code></pre>`;
        }
        return renderBlocks(part);
      })
      .join("");

    return sanitizeHtml(html);
  }

  function renderBlocks(text) {
    const lines = text.split("\n");
    const chunks = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();

      if (!trimmed) {
        index += 1;
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        chunks.push("<hr>");
        index += 1;
        continue;
      }

      const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        chunks.push(`<h${level}>${renderInline(headingMatch[2])}</h${level}>`);
        index += 1;
        continue;
      }

      if (trimmed.startsWith(">")) {
        const quoteLines = [];
        while (index < lines.length && lines[index].trim().startsWith(">")) {
          quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
          index += 1;
        }
        chunks.push(
          `<blockquote>${quoteLines.map((item) => renderParagraph(item)).join("")}</blockquote>`
        );
        continue;
      }

      if (/^[-*+]\s+/.test(trimmed)) {
        const items = [];
        while (index < lines.length && /^[-*+]\s+/.test(lines[index].trim())) {
          items.push(lines[index].trim().replace(/^[-*+]\s+/, ""));
          index += 1;
        }
        chunks.push(
          `<ul>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`
        );
        continue;
      }

      if (/^\d+\.\s+/.test(trimmed)) {
        const items = [];
        while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
          items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
          index += 1;
        }
        chunks.push(
          `<ol>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ol>`
        );
        continue;
      }

      const paragraphLines = [];
      while (
        index < lines.length &&
        lines[index].trim() &&
        !/^#{1,4}\s/.test(lines[index].trim()) &&
        !lines[index].trim().startsWith(">") &&
        !/^[-*+]\s+/.test(lines[index].trim()) &&
        !/^\d+\.\s+/.test(lines[index].trim()) &&
        !/^(-{3,}|\*{3,}|_{3,})$/.test(lines[index].trim())
      ) {
        paragraphLines.push(lines[index]);
        index += 1;
      }
      chunks.push(renderParagraph(paragraphLines.join("\n")));
    }

    return chunks.join("");
  }

  function renderToolContent(content) {
    const text = String(content || "").trim();
    if (!text) {
      return "";
    }
    try {
      const parsed = JSON.parse(text);
      return `<pre class="code-block"><code>${escapeHtml(
        JSON.stringify(parsed, null, 2)
      )}</code></pre>`;
    } catch (_error) {
      return renderMarkdown(text);
    }
  }

  window.BlueSnailMarkdown = {
    escapeHtml,
    renderMarkdown,
    renderToolContent,
  };
})();
