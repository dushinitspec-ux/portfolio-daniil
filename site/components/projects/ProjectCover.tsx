import Image from "next/image";

import type { ProjectImage } from "@/lib/projects";

/** Cover picture inside a frame; GSAP slides it up inside the frame when it scrolls into view. */
export function ProjectCover({
  image,
  sizes,
  priority = false,
}: {
  image: ProjectImage;
  sizes: string;
  priority?: boolean;
}) {
  return (
    <div data-mask className="relative aspect-[16/10] overflow-hidden border border-line bg-surface">
      <div data-mask-inner className="absolute inset-0">
        <Image
          src={image.src}
          alt={image.alt}
          fill
          sizes={sizes}
          priority={priority}
          className="object-cover transition-transform duration-700 ease-out group-hover:scale-[1.03]"
        />
      </div>
    </div>
  );
}
