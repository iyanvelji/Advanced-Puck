import { useState } from "react";

interface PlayerAvatarProps {
  src: string;
  name: string;
  isLeader?: boolean;
  size?: "sm" | "md";
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default function PlayerAvatar({
  src,
  name,
  isLeader = false,
  size = "md",
}: PlayerAvatarProps) {
  const [failed, setFailed] = useState(false);
  const dim = size === "sm" ? "h-8 w-8 text-[10px]" : "h-10 w-10 text-xs";

  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded-full border bg-[#05070a] ${dim} ${
        isLeader
          ? "border-sky-400/70 shadow-[0_0_16px_rgba(56,189,248,0.4)]"
          : "border-white/15"
      }`}
    >
      {!failed && src ? (
        <img
          src={src}
          alt={name}
          onError={() => setFailed(true)}
          className="h-full w-full object-cover object-top"
          loading="lazy"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center font-bold tracking-wider text-sky-300">
          {getInitials(name)}
        </div>
      )}
    </div>
  );
}
