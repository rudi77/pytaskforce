/**
 * Mention-context detection for the chat composer's ``@mention`` file
 * picker (Cowork-parity).
 *
 * Split into its own module so it can be unit-tested in isolation from
 * the React component — getting the off-by-one boundaries right (cursor
 * at start of @, cursor inside email-like ``user@host`` text, multi-
 * line prompts) is the kind of thing that bites silently when buried
 * inside a 200-line composer.
 */

export interface MentionContext {
  /** Index of the ``@`` character in the textarea value. */
  start: number;
  /** Substring between ``@`` and the current cursor (the filter typed
   *  so far — may be empty if the cursor is right after ``@``). */
  query: string;
}

/**
 * Detect whether the cursor is inside an active ``@mention`` token.
 *
 * Rules (kept narrow on purpose so the picker only triggers when the
 * user clearly *intends* to mention a file):
 *
 *   1. The ``@`` must be at the very start of the value, OR preceded by
 *      whitespace. This rejects ``some@email.com`` style strings: the
 *      ``@`` there has a letter to its left.
 *
 *   2. The query (text between ``@`` and cursor) must NOT contain
 *      whitespace. As soon as the user types a space, the mention is
 *      "completed" and the picker should close.
 *
 *   3. Newlines also terminate a mention — wrap-arounds shouldn't carry
 *      the picker across lines.
 *
 *   4. ``cursor === start`` (right after typing ``@``) is a valid
 *      mention with an empty query — the picker shows the root listing.
 *
 * Returns ``null`` when there's no active mention context.
 */
export function getMentionContext(
  value: string,
  cursor: number,
): MentionContext | null {
  if (cursor < 1) return null;
  // Walk back from cursor-1 looking for an ``@`` that meets the
  // boundary rules. Stop at the first whitespace — anything past it is
  // a different token.
  for (let i = cursor - 1; i >= 0; i--) {
    const ch = value[i];
    if (ch === "@") {
      const isBoundary = i === 0 || /\s/.test(value[i - 1]);
      if (!isBoundary) return null;
      const query = value.slice(i + 1, cursor);
      // Defensive: if anything snuck in here (newline pasted, …), reject.
      if (/[\s\n\r]/.test(query)) return null;
      return { start: i, query };
    }
    if (/[\s\n\r]/.test(ch)) {
      return null;
    }
  }
  return null;
}

/**
 * Build the new textarea value after a pick: replace the active mention
 * (``@partial``) with ``@<picked-path> `` and return the new value plus
 * the cursor position to set.
 *
 * A trailing space is appended so the user can keep typing without
 * having to add one — and so the picker auto-closes (a space terminates
 * the mention per ``getMentionContext``).
 */
export function applyMentionPick(
  value: string,
  ctx: MentionContext,
  pickedPath: string,
): { value: string; cursor: number } {
  const before = value.slice(0, ctx.start);
  const after = value.slice(ctx.start + 1 + ctx.query.length);
  const inserted = `@${pickedPath} `;
  return {
    value: before + inserted + after,
    cursor: before.length + inserted.length,
  };
}
