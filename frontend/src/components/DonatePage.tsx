interface DonatePageProps {
  onBack: () => void;
}

const KOFI_PAGE_URL = "https://ko-fi.com/advancedpuck";
const KOFI_EMBED_URL =
  "https://ko-fi.com/advancedpuck/?hidefeed=true&widget=true&embed=true&preview=true";

export default function DonatePage({ onBack }: DonatePageProps) {
  return (
    <div className="space-y-8">
      <div>
        <button
          type="button"
          onClick={onBack}
          className="cursor-pointer rounded-xl border border-sky-400/40 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-300 transition hover:bg-sky-500/20"
        >
          ← Back
        </button>
      </div>

      {/* Centered Header */}
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
          Donate
        </h1>
        <p className="mt-4 text-base leading-relaxed text-zinc-300 sm:text-lg">
          Donate to ensure the site remains free for everyone to use.
        </p>
      </div>

      {/* Embedded Ko-fi Widget Frame */}
      <div className="relative mx-auto max-w-2xl overflow-hidden rounded-2xl border border-sky-500/30 bg-[#0b0f17] p-2 shadow-[0_18px_55px_rgba(0,0,0,0.75)] sm:p-3">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent" />
        <div className="overflow-hidden rounded-xl bg-[#f9f9f9]">
          <iframe
            id="kofiframe"
            src={KOFI_EMBED_URL}
            className="w-full border-0"
            height={712}
            title="Support Advanced Puck on Ko-fi"
          />
        </div>
      </div>

      {/* Direct Ko-fi Fallback Link */}
      <p className="text-center text-xs text-zinc-500">
        Prefer to open Ko-fi in a new tab?{" "}
        <a
          href={KOFI_PAGE_URL}
          target="_blank"
          rel="noreferrer"
          className="text-sky-400 underline hover:text-sky-300"
        >
          ko-fi.com/advancedpuck ↗
        </a>
      </p>
    </div>
  );
}
