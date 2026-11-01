export function Placeholder({ title }: { title: string }) {
  return (
    <section>
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-slate-600">Coming in a later phase.</p>
    </section>
  );
}
