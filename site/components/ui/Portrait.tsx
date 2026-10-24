import Image from "next/image";

import photo from "@/public/images/daniil-dushin.png";

/**
 * The portrait in the hero: the photo in a circle, a thin concentric ring in the site's line
 * colour and the accent square as a small "online" mark, so it belongs to the same system as
 * the logo and the status line. The photo's own gold ring is cropped away.
 */
export function Portrait({ alt }: { alt: string }) {
  return (
    <figure className="portrait-in relative w-[8.5rem] shrink-0 sm:w-[10rem] md:w-full">
      <div className="rounded-full border border-line p-2 md:p-3">
        {/* The circle clips the photo, which MotionRoot slowly zooms while the hero scrolls away
            ("isolate" keeps Safari clipping a transformed child to the rounded corners). */}
        <div className="isolate overflow-hidden rounded-full">
          <div data-portrait-img>
            <Image
              src={photo}
              alt={alt}
              // Not "priority": the hero renders two copies (phone / desktop layout) and only one
              // is visible; eager loading without a preload keeps the hidden one from competing.
              loading="eager"
              placeholder="blur"
              sizes="(min-width: 768px) 24vw, 10rem"
              className="aspect-square w-full rounded-full bg-[#0b0b0d] object-cover"
            />
          </div>
        </div>
      </div>
      <span
        aria-hidden="true"
        className="portrait-mark absolute bottom-[13%] right-[9%] h-3 w-3 bg-accent outline outline-4 outline-bg md:h-4 md:w-4 md:outline-[6px]"
      />
    </figure>
  );
}
