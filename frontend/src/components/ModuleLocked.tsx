import { MODULE_NAMES, type Module } from "@/lib/api";
import Button from "./Button";

// The locked page for an unlicensed module (afterRoute() in the reference).
export default function ModuleLocked({ module }: { module: Module }) {
  return (
    <section>
      <div className="wrap">
        <div className="banner no">
          403 MODULE_NOT_LICENSED - The {MODULE_NAMES[module]} module is not licensed for this installation.
        </div>
        <p>This part of the software is not included in the licence.</p>
        <div className="acts" style={{ marginTop: 20 }}>
          <Button href="/">Go home</Button>
        </div>
      </div>
    </section>
  );
}
