/**
 * Rendering for the agent grounding markers.
 *
 * An agent wraps a span it inferred rather than sourced in `[? ... ?]` (see
 * `GROUNDING_POLICY` in `backend/app/agents/prompts.py`). Here that span becomes
 * a highlighted `<mark>` with a trailing "(?)", so a reader can tell at a glance
 * which parts of an answer the model stands behind.
 *
 * A second, looser form is also honoured: a sentence ending in a bare `(?)`.
 * Small local models drop the wrapper often enough that supporting only the
 * strict form would fail silently — the guess would render as a flat assertion,
 * which is the exact outcome the markers exist to prevent.
 *
 * Implemented as a remark plugin over the mdast tree rather than a string
 * pre-pass so that code is never touched: fenced blocks and inline spans are
 * `code`/`inlineCode` nodes, and this only ever descends into `text`.
 */

/** The literals the backend emits. Keep in sync with `core/constants.py`. */
const OPEN = '[?';
const CLOSE = '?]';
const BARE = '(?)';

/** Marks a span the walker replaced, so the renderer can style it. */
export const UNCERTAIN_CLASS = 'uncertain';

interface TextNode {
  type: 'text';
  value: string;
}

/**
 * An `emphasis` node redirected to `<mark>` at the rehype boundary. Reusing a
 * standard mdast type (rather than inventing one) is what lets this work with
 * no custom rehype handler: remark-rehype reads `data.hName`/`data.hProperties`
 * off any node it already knows how to convert.
 */
interface MarkNode {
  type: 'emphasis';
  data: { hName: 'mark'; hProperties: { className: string } };
  children: TextNode[];
}

type InlineNode = TextNode | MarkNode;

interface ParentNode {
  type: string;
  children?: unknown[];
  value?: string;
}

function textNode(value: string): TextNode {
  return { type: 'text', value };
}

function markNode(value: string): MarkNode {
  return {
    type: 'emphasis',
    data: { hName: 'mark', hProperties: { className: UNCERTAIN_CLASS } },
    children: [textNode(value)],
  };
}

/**
 * Walk back from `end` to the start of the sentence containing it.
 *
 * Used only for the bare `(?)` fallback, where the model marked a sentence
 * without saying where it begins. Stops at a terminator, a line break, or the
 * start of the node — so a sentence split across inline formatting highlights
 * from the last such boundary rather than from its true start. That under-marks
 * in a rare case; it never over-marks into a neighbouring sentence.
 */
function sentenceStart(text: string, end: number): number {
  for (let i = end - 1; i >= 0; i -= 1) {
    const ch = text[i];
    if (ch === '\n') return i + 1;
    // A terminator only ends a sentence when whitespace follows it, which keeps
    // "v2.4.1" and "e.g." from being read as boundaries.
    if ((ch === '.' || ch === '!' || ch === '?') && /\s/.test(text[i + 1] ?? '')) {
      return i + 1;
    }
  }
  return 0;
}

/**
 * Split one text node's value into plain and highlighted parts.
 *
 * `tolerateOpen` is for the streaming preview: mid-stream the closing `?]` may
 * not have arrived yet, and without this the reader watches a raw `[?` sit on
 * screen until it does.
 */
function splitUncertain(value: string, tolerateOpen: boolean): InlineNode[] {
  const out: InlineNode[] = [];
  let rest = value;

  while (rest.length > 0) {
    const open = rest.indexOf(OPEN);
    if (open === -1) break;
    const close = rest.indexOf(CLOSE, open + OPEN.length);

    if (close === -1) {
      if (!tolerateOpen) break;
      // Unclosed: highlight everything still to come and stop.
      pushText(out, rest.slice(0, open));
      const tail = rest.slice(open + OPEN.length).trim();
      if (tail) out.push(markNode(tail));
      return out;
    }

    pushText(out, rest.slice(0, open));
    const inner = rest.slice(open + OPEN.length, close).trim();
    if (inner) out.push(markNode(inner));
    rest = rest.slice(close + CLOSE.length);
  }

  if (rest) out.push(...splitBare(rest));
  return out;
}

/** The bare `(?)` fallback, applied to whatever the wrapper pass left behind. */
function splitBare(value: string): InlineNode[] {
  const out: InlineNode[] = [];
  let rest = value;

  for (;;) {
    const at = rest.indexOf(BARE);
    if (at === -1) break;
    // Step over the marked sentence's own trailing whitespace and terminator
    // before searching backwards — otherwise that terminator reads as the
    // boundary and the sentence collapses to nothing.
    let end = at;
    while (end > 0 && /\s/.test(rest[end - 1] ?? '')) end -= 1;
    if (end > 0 && '.!?'.includes(rest[end - 1] ?? '')) end -= 1;
    // Whitespace between the boundary and the sentence stays *outside* the
    // highlight — inside, it would be trimmed away and the two sentences would
    // render flush against each other.
    let start = sentenceStart(rest, end);
    while (start < at && /\s/.test(rest[start] ?? '')) start += 1;
    pushText(out, rest.slice(0, start));
    // The literal "(?)" is dropped here because the renderer appends its own.
    const sentence = rest.slice(start, at).trimEnd();
    if (sentence) out.push(markNode(sentence));
    else pushText(out, rest.slice(start, at + BARE.length));
    rest = rest.slice(at + BARE.length);
  }

  if (rest) pushText(out, rest);
  return out;
}

function pushText(out: InlineNode[], value: string): void {
  if (value) out.push(textNode(value));
}

function isParent(node: unknown): node is ParentNode {
  return typeof node === 'object' && node !== null && 'type' in node;
}

/** Recursively rewrite `text` children in place; never descends into code. */
function transform(node: ParentNode, tolerateOpen: boolean): void {
  const children = node.children;
  if (!Array.isArray(children)) return;

  const next: unknown[] = [];
  for (const child of children) {
    if (!isParent(child)) {
      next.push(child);
      continue;
    }
    if (child.type === 'text' && typeof child.value === 'string') {
      // Nothing to mark: keep the original node, positions and all, so an
      // unmarked answer renders through a tree this plugin never touched.
      if (!child.value.includes(OPEN) && !child.value.includes(BARE)) {
        next.push(child);
        continue;
      }
      next.push(...splitUncertain(child.value, tolerateOpen));
      continue;
    }
    // `code` and `inlineCode` carry their content on `value`, not in `children`,
    // so this recursion structurally cannot reach into them.
    transform(child, tolerateOpen);
    next.push(child);
  }
  node.children = next;
}

interface UncertaintyOptions {
  /** Highlight an unclosed trailing marker (streaming). Default `false`. */
  tolerateOpen?: boolean;
}

/** remark plugin factory. Pass the result to `remarkPlugins`. */
export function remarkUncertainty({ tolerateOpen = false }: UncertaintyOptions = {}) {
  return function transformer(tree: unknown): void {
    if (isParent(tree)) transform(tree, tolerateOpen);
  };
}

/**
 * Flatten the markers for plain-text use (copy to clipboard).
 *
 * `[? late 2023 ?]` becomes `late 2023 (?)`, matching what is on screen — a
 * pasted answer should not leak the wire format, nor lose the caveat.
 */
export function plainTextUncertainty(text: string): string {
  const pattern = new RegExp(
    `${escapeRegExp(OPEN)}\\s*([\\s\\S]*?)\\s*${escapeRegExp(CLOSE)}`,
    'g',
  );
  return text.replace(pattern, (_match, inner: string) => `${inner} ${BARE}`);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
