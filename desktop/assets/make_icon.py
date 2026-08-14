"""Genera l'icona dell'applicazione e la favicon dell'interfaccia.

    python make_icon.py

Icona provvisoria, pensata per essere sostituita da quella definitiva del
cliente: quadrato arrotondato indaco con la "P" di Promemoria e un segno di
spunta.

Le due immagini nascono qui insieme di proposito: sono la stessa identità vista
in due posti — la barra delle applicazioni e la scheda del browser — e quando
si generavano separatamente finivano per divergere.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
BG = (79, 70, 229)
FG = (255, 255, 255)
LETTER = "P"

ICON = Path(__file__).with_name("icon.ico")
#: La favicon serve al frontend, che sta in un altro punto del repository.
FAVICON = Path(__file__).resolve().parents[2] / "frontend" / "public" / "favicon.ico"

#: Misure incluse nell'.ico dell'applicazione. Ce ne sono tante perché Windows
#: pesca quella giusta a seconda del posto: 16 per la tray, 32 per la barra,
#: 256 per il toast delle notifiche.
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
FAVICON_SIZES = [(16, 16), (32, 32), (48, 48)]


def font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


#: Sotto questa misura la spunta non si legge più: si impasta sulla lettera e
#: produce una macchia. Le icone piccole portano solo la "P", più grande.
SOGLIA_SPUNTA = 32


def disegna(*, spunta: bool) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=int(SIZE * 0.22), fill=BG)

    # Senza la spunta la lettera ha tutto il riquadro per sé, e va ingrandita e
    # ricentrata: è quello che rende leggibile l'icona nella tray.
    altezza = 0.58 if spunta else 0.72
    centro_y = 0.44 if spunta else 0.48

    # La "P" sta un filo a sinistra del centro: ha l'occhiello a destra e il
    # gambo a sinistra, quindi centrata sul riquadro sembrerebbe spostata.
    letter = font(int(SIZE * altezza))
    draw.text((SIZE * 0.47, SIZE * centro_y), LETTER, font=letter, fill=FG, anchor="mm")

    if spunta:
        # Segno di spunta in basso a destra: "fatto", il senso di un promemoria.
        draw.line(
            [(SIZE * 0.60, SIZE * 0.74), (SIZE * 0.68, SIZE * 0.82), (SIZE * 0.83, SIZE * 0.62)],
            fill=FG,
            width=int(SIZE * 0.055),
            joint="curve",
        )
    return image


def salva(percorso: Path, misure: list[tuple[int, int]]) -> None:
    """Scrive un .ico in cui ogni misura è disegnata apposta per la sua taglia.

    Pillow, da solo, rimpicciolirebbe una sola immagine per tutte le misure. Le
    varianti già pronte passate in `append_images` vengono invece usate così
    come sono, ed è l'unico modo per avere un'icona piccola diversa da quella
    grande dentro allo stesso file.

    L'immagine di partenza deve essere la più grande di tutte: Pillow scarta in
    silenzio le misure richieste che la superano, e ci si ritrova con un .ico
    di una riga sola.
    """
    grande = disegna(spunta=True)
    piccola = disegna(spunta=False)

    varianti = [
        (grande if larghezza >= SOGLIA_SPUNTA else piccola).resize((larghezza, altezza))
        for larghezza, altezza in misure
    ]
    percorso.parent.mkdir(parents=True, exist_ok=True)
    grande.save(percorso, format="ICO", sizes=misure, append_images=varianti)

    scritte = sorted(Image.open(percorso).info["sizes"])
    if scritte != sorted(misure):
        raise SystemExit(f"{percorso.name}: attese {sorted(misure)}, scritte {scritte}")


if __name__ == "__main__":
    salva(ICON, ICON_SIZES)
    print(f"icona creata:   {ICON}")

    salva(FAVICON, FAVICON_SIZES)
    print(f"favicon creata: {FAVICON}")
