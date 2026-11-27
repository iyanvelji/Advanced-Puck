interface DonateBannerProps {
  onOpenDonate: () => void;
  className?: string;
}

export default function DonateBanner({
  onOpenDonate,
  className = "",
}: DonateBannerProps) {
  return (
    <section
      className={`relative overflow-hidden rounded-2xl border border-sky-500/25 bg-gradient-to-r from-sky-500/[0.12] via-[#0b0f17] to-[#0b0f17] px-6 py-6 shadow-[0_14px_45px_rgba(0,0,0,0.7)] sm:px-8 sm:py-7 ${className}`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent" />

      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="mt-1.5 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
            Donate
          </h2>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-zinc-400">
            Donate to ensure the site remains free for everyone to use.
          </p>
        </div>

        <button
          type="button"
          onClick={onOpenDonate}
          className="group inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full border border-sky-400/50 bg-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-[0_0_24px_rgba(56,189,248,0.28)] transition-all hover:bg-sky-500"
        >
          <span>Donate today</span>
          <span className="transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5">
            ↗
          </span>
        </button>
      </div>
    </section>
  );
}
