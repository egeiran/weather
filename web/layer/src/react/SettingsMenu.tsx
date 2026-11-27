import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

import type { WeatherState } from '../core/WeatherLayers';
import type { ArrowsSetting, ParticlesSetting } from '../core/WeatherLayers';
import { useWeatherI18n } from './i18n';
import { GearIcon } from './icons';

/** Gear button with a popover: motion toggles plus any extra sections the host passes in. */
export function SettingsMenu(props: {
  state: WeatherState | null;
  particles: ParticlesSetting;
  onParticles: (p: ParticlesSetting) => void;
  arrows?: ArrowsSetting;
  onArrows: (a: ArrowsSetting) => void;
  children?: ReactNode;
  defaultOpen?: boolean;
}) {
  const { t } = useWeatherI18n();
  const [open, setOpen] = useState(props.defaultOpen ?? false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown);
    };
  }, [open]);
  const p = props.state?.particles;
  const reason =
    props.particles === 'auto' && p?.reason === 'reduced-motion'
      ? t('particles.reducedMotion')
      : props.particles === 'auto' && p?.reason === 'slow-connection'
        ? t('particles.slowConnection')
        : null;
  return (
    <div className="wl-settings" ref={ref}>
      <button
        type="button"
        className="wl-round-btn"
        aria-expanded={open}
        aria-controls={id}
        aria-label={open ? t('settings.close') : t('settings.open')}
        onClick={() => setOpen(!open)}
      >
        <GearIcon />
      </button>
      {open && (
        <div className="wl-popover" id={id} role="dialog" aria-label={t('settings.title')}>
          <section>
            <h3>{t('settings.motion')}</h3>
            <label className="wl-switch">
              <input
                type="checkbox"
                checked={p ? p.enabled : props.particles !== false}
                onChange={(e) => props.onParticles(e.target.checked)}
              />
              <span>{t('particles.toggle')}</span>
            </label>
            {reason && <p className="wl-muted wl-small">{reason}</p>}
            <label className="wl-switch">
              <input
                type="checkbox"
                checked={props.state?.arrows ?? props.arrows === true}
                onChange={(e) => props.onArrows(e.target.checked)}
              />
              <span>{t('arrows.toggle')}</span>
            </label>
          </section>
          {props.children}
        </div>
      )}
    </div>
  );
}
