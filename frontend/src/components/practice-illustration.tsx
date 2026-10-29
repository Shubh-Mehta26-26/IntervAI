import { Icon } from "./ui/icon";

/** Decorative CSS sculpture; no downloads or canvas rendering loop. */
export function PracticeIllustration() {
  return <div className="future-sculpture" aria-hidden="true">
    <div className="sculpture-halo" />
    <div className="sculpture-floor" />
    <div className="sculpture-portal"><span /></div>
    <div className="sculpture-ring" />
    <div className="sculpture-sphere sphere-pearl" />
    <div className="sculpture-sphere sphere-violet" />
    <div className="sculpture-cube" />
    <div className="sculpture-step step-one" />
    <div className="sculpture-step step-two" />
    <div className="sculpture-step step-three" />
    <div className="sculpture-label label-voice"><span className="sculpture-label-icon"><Icon name="mic" size={18}/></span><span><small>YOUR PRACTICE SPACE</small><strong>Confidence starts here.</strong></span><span className="sculpture-wave">{[1,2,3,4,5].map(n => <i key={n}/>)}</span></div>
    <div className="sculpture-label label-growth"><Icon name="arrow" size={18}/><span>One step closer.</span></div>
  </div>;
}
