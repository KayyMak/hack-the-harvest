/** A clearly marked slot for data the team has not exported yet. Never shows made-up numbers. */
export function Pending({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="pending" role="note">
      <div className="pending__head">
        <span className="pending__tag">Pending</span>
        <span className="pending__title">{title}</span>
      </div>
      <p className="pending__body">{children}</p>
    </div>
  )
}
