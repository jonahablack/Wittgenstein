import { cx } from "../lib";

/** Tractatus Logico-Philosophicus, proposition 7: the original, with the English. */
export function Epigraph({ className, quiet }: { className?: string; quiet?: boolean }) {
  return (
    <figure className={cx("text-center", className)}>
      <blockquote
        lang="de"
        className={cx(
          "font-serif text-balance italic tracking-[0.01em]",
          quiet ? "text-lg text-ink-3 sm:text-xl" : "text-2xl text-ink-2 sm:text-[1.7rem]",
        )}
      >
        Wovon man nicht sprechen kann, darüber muss man schweigen.
      </blockquote>
      <figcaption className={cx("mt-3 text-sm", quiet ? "text-ink-4" : "text-ink-3")}>
        Whereof one cannot speak, thereof one must be silent.
        <span className="mt-1 block text-xs tracking-wide text-ink-4 uppercase">
          Wittgenstein, Tractatus Logico-Philosophicus, 7
        </span>
      </figcaption>
    </figure>
  );
}
