import type { NavSection } from "../types/standings";
import puckIcon from "../assets/puck.jpg";

interface NavbarProps {
  activeSection: NavSection;
  onSelectSection: (section: NavSection) => void;
}

interface NavItem {
  id: NavSection;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "teams", label: "Teams" },
  { id: "players", label: "Players" },
];

export default function Navbar({
  activeSection,
  onSelectSection,
}: NavbarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-sky-500/15 bg-[#05070a]/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <img
            src={puckIcon}
            alt="Advanced Puck"
            className="h-9 w-9 rounded-xl border border-sky-400/40 object-cover shadow-[0_0_16px_rgba(56,189,248,0.2)]"
          />
          <span className="text-lg font-bold tracking-tight text-white">
            Advanced Puck
          </span>
        </div>

        <nav className="flex items-center gap-2">
          {NAV_ITEMS.map((item) => {
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectSection(item.id)}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                  isActive
                    ? "border border-sky-400/50 bg-sky-500/15 text-sky-300 shadow-[0_0_14px_rgba(56,189,248,0.18)]"
                    : "border border-transparent text-zinc-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
