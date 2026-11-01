/** Shows rendered email HTML. sandbox="" blocks scripts, forms and navigation: the HTML includes vendor-supplied text. */
export function EmailFrame({ subject, to, html }: { subject: string | null; to: string | null; html: string }) {
  return (
    <div>
      <dl className="mb-3 grid grid-cols-[4rem_1fr] gap-y-1 text-sm">
        <dt className="text-slate-600">To</dt><dd>{to ?? ""}</dd>
        <dt className="text-slate-600">Subject</dt><dd className="font-medium">{subject ?? ""}</dd>
      </dl>
      <iframe title="Email as rendered" sandbox="" srcDoc={html} className="h-[28rem] w-full rounded border border-slate-300 bg-white" />
    </div>
  );
}
