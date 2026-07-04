/** Decorative "+" marks at the corners of a card, à la Codity. Parent must
 * be `position: relative`. */
export function PlusMarks() {
  return (
    <>
      <PlusIcon className="plus-mark -top-1.5 -left-1.5" />
      <PlusIcon className="plus-mark -top-1.5 -right-1.5" />
      <PlusIcon className="plus-mark -bottom-1.5 -left-1.5" />
      <PlusIcon className="plus-mark -bottom-1.5 -right-1.5" />
    </>
  )
}

function PlusIcon({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 14 14" fill="none" className={className} aria-hidden="true">
      <path d="M7 1V13M1 7H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}
