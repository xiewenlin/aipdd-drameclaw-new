import type { CSSProperties } from "react";
import styles from "./sixth-showcase-screen.module.css";
import { cinematicVideoLibrary } from "./media";

const works = cinematicVideoLibrary;

function FilmShowcase({
  sequenceProgress,
  onWatch,
}: {
  sequenceProgress: number;
  onWatch: () => void;
}) {
  const translate = -sequenceProgress * 155;

  return (
    <div className={styles.filmStage}>
      <div className={styles.filmRail} style={{ "--film-shift": `${translate}vw` } as CSSProperties}>
        {works.map((work) => (
          <article className={styles.filmCard} key={work.id}>
            <div className={styles.filmMedia}>
              <video src={work.video} muted loop playsInline autoPlay preload="metadata" />
              <div className={styles.cardScrim} />
            </div>
            <div className={styles.filmMeta}>
              <span>{work.type}</span>
              <span>{work.stat}</span>
            </div>
            <div className={styles.filmCopy}>
              <h3>{work.title}</h3>
              <p>{work.logline}</p>
            </div>
            <button
              type="button"
              className={styles.watchButton}
              onClick={onWatch}
              aria-label="立即观看社区作品"
            >
              <span>立即观看</span>
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}

export function SixthShowcaseScreen({
  exitProgress = 0,
  progress,
  sequenceProgress,
  onWatch,
}: {
  exitProgress?: number;
  progress: number;
  sequenceProgress: number;
  onWatch: () => void;
}) {
  if (exitProgress >= 0.99) return null;
  if (progress <= 0.01) return null;

  const style = {
    "--sixth-opacity": progress * (1 - exitProgress),
    "--sixth-offset": `${(1 - progress) * 42 - exitProgress * 24}px`,
    "--sixth-blur": `${exitProgress * 8}px`,
    pointerEvents: progress > 0.5 && exitProgress < 0.12 ? "auto" : "none",
  } as CSSProperties;

  return (
    <section className={styles.layer} style={style}>
      <div className={styles.header}>
        <p>SHOWCASE 06</p>
        <h2>按剧集推进到成片</h2>
        <span>无限画布支持多参、多节点、多版本探索，并在确认后把结果写回主流程，保留自由创作空间</span>
      </div>

      <FilmShowcase sequenceProgress={sequenceProgress} onWatch={onWatch} />
    </section>
  );
}
