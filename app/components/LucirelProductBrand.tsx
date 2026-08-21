import { LUCIREL_WAVE_GATE_ICON } from "./lucirelBrandAsset";

export function LucirelProductBrand({ large = false }: { large?: boolean }) {
  return (
    <span className={`lucirel-product-brand${large ? " large" : ""}`}>
      <span
        className="lucirel-brand-mark"
        role="img"
        aria-label="Lucirel Wave Gate"
        style={{ backgroundImage: `url(${LUCIREL_WAVE_GATE_ICON})` }}
      />
      <span className="lucirel-brand-copy">
        <strong>LessonForge</strong>
        <span>TW 教材工作台 · by Lucirel</span>
      </span>
    </span>
  );
}
