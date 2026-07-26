/**
 * Give an agent's GFM table the blank line it needs to be parsed as a table.
 *
 * A table is a block-level construct: its header row has to start a new block.
 * Models routinely write one straight under a heading or a list item —
 *
 *     2. **Supporting Evidence**
 *     | Source | Summary | Date/Note |
 *     |--------|--------------|-----------|
 *
 * — and without the blank line the header is a lazy continuation of the
 * paragraph above it. remark then never sees a table at all: every row is
 * folded into that paragraph and the reader gets a wall of text with pipes and
 * dashes in it, which is exactly what an observed `seo` answer looked like.
 *
 * Fixed here rather than in the prompt because the prompt is not a reliable
 * lever on a local model — four escalating rules failed to change a different
 * behaviour the same night — and because the same answer is served to any API
 * consumer, so the renderer should be able to cope with plain-but-imperfect
 * markdown.
 *
 * The transform only ever *inserts a blank line*. It never removes, reorders or
 * rewrites content, so the worst case for a false positive is one extra
 * paragraph break.
 */

/**
 * A GFM delimiter row: `|---|---|`, `| :--- | ---: |`, outer pipes optional.
 *
 * Indented four spaces or more it would be an indented code block, hence the
 * `{0,3}` bound. A bare `---` (thematic break, or a setext underline) is
 * excluded by the caller, which requires a pipe on the line.
 */
const DELIMITER_ROW = /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;

/** Opening or closing fence of a fenced code block. */
const CODE_FENCE = /^ {0,3}(`{3,}|~{3,})/;

function isDelimiterRow(line: string): boolean {
  return line.includes('|') && DELIMITER_ROW.test(line);
}

function isHeaderRow(line: string): boolean {
  return line.includes('|') && line.trim() !== '' && !isDelimiterRow(line);
}

/**
 * Insert a blank line before any table header row that is glued to the text
 * above it. Content inside fenced code blocks is left exactly as written.
 */
export function normalizeMarkdownTables(markdown: string): string {
  if (!markdown.includes('|')) return markdown;

  const lines = markdown.split('\n');
  const out: string[] = [];
  let inFence = false;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    if (CODE_FENCE.test(line)) {
      inFence = !inFence;
      out.push(line);
      continue;
    }

    // A table is recognised by its delimiter row, so the header is the line
    // already pushed. Insert before that header, not before the delimiter.
    if (!inFence && i > 0 && isDelimiterRow(line) && isHeaderRow(lines[i - 1])) {
      const headerIndex = out.length - 1;
      const preceding = out[headerIndex - 1];
      if (preceding !== undefined && preceding.trim() !== '') {
        out.splice(headerIndex, 0, '');
      }
    }

    out.push(line);
  }

  return out.join('\n');
}
