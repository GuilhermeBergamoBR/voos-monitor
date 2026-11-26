import Link from "next/link";
import WatchForm from "../WatchForm";

export default function NewWatch() {
  return (
    <main className="mx-auto max-w-xl p-4 sm:p-6">
      <Link href="/" className="text-sm text-sky-700">← voltar</Link>
      <h1 className="my-4 text-xl font-semibold">Novo monitoramento</h1>
      <WatchForm watch={null} />
    </main>
  );
}
