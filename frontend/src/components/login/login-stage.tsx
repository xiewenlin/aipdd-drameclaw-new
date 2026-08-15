// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
// import { MessageCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CommunityShowcase } from "./community-showcase";
import LightRays from "./light-rays";
import SplitText from "@/components/react-bits/split-text";
import { PRODUCT_MANUAL_URL } from "@/lib/product-manual";
import styles from "./login.module.css";

export function Brand({ className }: { className?: string }) {
  return (
    <div className={className ?? styles.brand} aria-label="DramaClaw">
      <img
        className={styles.brandLogo}
        src="/brand/dramaclaw-wordmark.png"
        alt=""
        aria-hidden="true"
      />
    </div>
  );
}

/**
 * Stage contents — render inside an element already styled with `styles.stage`.
 */
export function LoginStageContent({
  onStart,
}: {
  onStart: () => void;
}) {
  const { t } = useTranslation();

  return (
    <>
      <div className={styles.stageLightRays} aria-hidden="true">
        <LightRays
          raysOrigin="top-center"
          raysColor="#ffffff"
          raysSpeed={1}
          lightSpread={0.5}
          rayLength={3}
          pulsating={false}
          fadeDistance={1}
          saturation={1}
          followMouse={false}
          mouseInfluence={0.1}
          noiseAmount={0}
          distortion={0}
        />
      </div>

      <div className={styles.stageInner}>
        <div className={styles.stageTopBar}>
          <Brand />
          <div className={styles.stageActions}>
{/*
            <div className={styles.businessWechat}>
              <button
                type="button"
                className={styles.businessWechatTrigger}
                aria-label={t("auth.businessWechat.open")}
              >
                <MessageCircle aria-hidden="true" />
                {t("auth.businessWechat.label")}
              </button>
              <div
                className={styles.businessWechatPopover}
                role="dialog"
                aria-label={t("auth.businessWechat.qrAlt")}
              >
                <div className={styles.businessWechatPanel}>
                  <img
                    src="https://nfg-web-assets.cdnfg.com/dramaclaw/contact/wechat.png"
                    alt={t("auth.businessWechat.qrAlt")}
                    draggable={false}
                  />
                  <div className={styles.businessWechatText}>
                    <p className={styles.businessWechatTitle}>
                      {t("auth.businessWechat.title")}
                    </p>
                    <p className={styles.businessWechatSubtitle}>
                      {t("auth.businessWechat.subtitle")}
                    </p>
                    <p className={styles.businessWechatNote}>
                      {t("auth.businessWechat.note")}
                    </p>
                  </div>
                </div>
              </div>
            </div>
*/}
            {/* GitHub 链接暂时隐藏
            <a
              className={styles.githubLink}
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              title="GitHub"
              aria-label="GitHub"
            >
              <GithubMark />
              {stars !== null && (
                <>
                  <span className={styles.githubStarLabel}>
                    {t("auth.github.star")}
                  </span>
                  <span className={styles.githubStars}>{formatStars(stars)}</span>
                </>
              )}
            </a>
            */}
          </div>
        </div>

        <div className={styles.hero}>
          <SplitText
            tag="h1"
            text={t("auth.stage.headlines.createUniverse")}
            className={styles.heroTitle}
            delay={70}
            duration={0.8}
            ease="power3.out"
            splitType="chars"
            from={{ opacity: 0, y: 36 }}
            to={{ opacity: 1, y: 0 }}
            threshold={0.1}
            rootMargin="-100px"
            textAlign="center"
          />
          <p className={styles.heroSubtitle}>
            <span className={styles.heroSubtitlePrefix}>
              {t("auth.stage.subtitlePrefix")}
            </span>
            <span className={styles.heroSubtitleBrand}>
              {t("auth.stage.subtitleBrand")}
            </span>
            <span className={styles.heroSubtitleSuffix}>
              {t("auth.stage.subtitleSuffix")}
            </span>
          </p>
          <div className={styles.heroActions}>
            <button
              type="button"
              className={styles.heroPrimary}
              onClick={onStart}
            >
              {t("auth.stage.start")}
            </button>
            <a
              className={styles.heroSecondary}
              href={PRODUCT_MANUAL_URL}
              target="_blank"
              rel="noopener noreferrer"
              title={t("auth.openManual")}
              aria-label={t("auth.openManual")}
            >
              {t("auth.learnMore")}
            </a>
          </div>
        </div>

        <CommunityShowcase />
      </div>
    </>
  );
}
