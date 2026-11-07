/**
 * Client half of dsh-linus-brand.
 *
 * The skin renders the composer pet from an inline `--dsh-claude-mascot-sheet`
 * custom property plus a set of geometry variables. A stylesheet rule carrying
 * `!important` outranks those inline declarations, so one rule per animation
 * state swaps the artwork while the skin keeps driving its own frame offsets.
 *
 * The second half of each rule fades the sprite in when the state changes, so a
 * switch (idle -> typing, typing -> happy) reads as a soft cross-fade instead of
 * a hard cut. Only opacity and a 4px translate are animated — never scale — so
 * the pet never appears to grow or shrink.
 */
window.__ModuleLoader__.load({
  id: "dsh-linus-brand",
  factory(require) {
    const STATES = [
      "idle",
      "idle-look",
      "idle-spout",
      "thinking",
      "typing",
      "music",
      "conducting",
      "building",
      "error",
      "happy",
      "notification",
      "compacting",
      "sleeping",
      "waking",
      "poke-left",
      "poke-right",
      "tickle",
      "drag",
    ];

    const REV = "anim4";

    const keyframes = [
      "@keyframes dsh-linus-pet-in{",
      "from{opacity:0;transform:translateY(4px)}",
      "to{opacity:1;transform:translateY(0)}",
      "}",
    ].join("");

    const rules = STATES.map(
      (state) =>
        `.dsh-claude-deepy[data-animation="${state}"]{--dsh-claude-mascot-sheet:url("/dsh-linus-brand/assets/${state}.svg?v=${REV}")!important}` +
        `.dsh-claude-deepy[data-animation="${state}"]>.dsh-claude-deepy-sprite{animation:dsh-linus-pet-in 280ms ease-out}`,
    ).join("\n");

    return {
      apply(ctx) {
        ctx.effect(() => {
          const style = document.createElement("style");
          style.setAttribute("data-dsh-linus-brand", "");
          style.textContent = `${keyframes}\n${rules}`;
          document.head.append(style);
          return () => {
            style.remove();
          };
        });
      },
    };
  },
});
