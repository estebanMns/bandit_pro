import { describe, expect, it } from "vitest";
import { canWatch, endReasonLabel, isOpen, sessionStatusLabel } from "./labels";
import { resolveUrl } from "./whep";

describe("estados de sesión móvil", () => {
  it("solo pide video cuando el teléfono ya publica", () => {
    expect(canWatch("awaiting_device")).toBe(false);
    expect(canWatch("accepted")).toBe(false);
    expect(canWatch("connecting")).toBe(true);
    expect(canWatch("live")).toBe(true);
    expect(canWatch("ended")).toBe(false);
  });

  it("distingue sesiones abiertas de cerradas", () => {
    expect(isOpen("requested")).toBe(true);
    expect(isOpen("reconnecting")).toBe(true);
    expect(isOpen("rejected")).toBe(false);
    expect(isOpen("expired")).toBe(false);
  });

  it("explica por qué terminó", () => {
    expect(endReasonLabel("not_answered")).toMatch(/a tiempo/);
    expect(endReasonLabel(null)).toBeNull();
    expect(endReasonLabel("desconocido")).toBeNull();
    expect(sessionStatusLabel("live")).toBe("Transmisión activa");
  });
});

describe("recurso WHEP", () => {
  it("resuelve la cabecera Location relativa al endpoint", () => {
    expect(resolveUrl("https://bandit.example/media/mobile/abc/whep", "/media/mobile/abc/whep/x")).toBe(
      "https://bandit.example/media/mobile/abc/whep/x",
    );
    expect(resolveUrl("https://bandit.example/media/mobile/abc/whep", null)).toBeNull();
  });
});
