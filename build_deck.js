// build_deck.js — Fellowship Report Slide Deck
// 22-slide PowerPoint for the NYU Africa House Fellowship report.
// Audience: non-technical (academics across disciplines + administrators).

const pptxgen = require("pptxgenjs");
const path = require("path");

const ROOT = __dirname;
const FIG = (name) => path.join(ROOT, "outputs", "figures", name);

// ---------- Color palette ----------
const C = {
  BG_DARK:    "2C3E50",
  BG_LIGHT:   "FAF6F0",
  TERRACOTTA: "B85042",
  CHARCOAL:   "1F2937",
  WHITE:      "FFFFFF",
  SAGE:       "7CA982",
  SLATE:      "475569",
  MUTED:      "64748B",
  CALLOUT_BG: "F5E8D3",
  ACCENT_GOLD:"D4A464",
};

const FONT_HEAD = "Georgia";
const FONT_BODY = "Calibri";

// ---------- Initialize ----------
let pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Olalekan Bello";
pres.title = "Chasing Pavements — Fellowship Report";

const W = 10, H = 5.625;
const TOTAL = 21;
const FOOTER_LABEL = "Chasing Pavements  ·  NYU Africa House Fellowship";

// ---------- Helpers ----------
function addAccentBar(slide) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: H,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });
}

function addFooter(slide, slideNum) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: H - 0.36, w: W - 1.0, h: 0.012,
    fill: { color: C.TERRACOTTA, transparency: 60 }, line: { type: "none" },
  });
  slide.addText(FOOTER_LABEL, {
    x: 0.6, y: H - 0.30, w: 6, h: 0.25,
    fontSize: 9, fontFace: FONT_BODY, color: C.MUTED, italic: true, margin: 0,
  });
  slide.addText(`${slideNum} / ${TOTAL}`, {
    x: W - 1.0, y: H - 0.30, w: 0.6, h: 0.25,
    fontSize: 9, fontFace: FONT_BODY, color: C.MUTED, align: "right", margin: 0,
  });
}

function addTitle(slide, title) {
  slide.addText(title, {
    x: 0.55, y: 0.30, w: W - 1.0, h: 0.7,
    fontSize: 30, fontFace: FONT_HEAD, color: C.CHARCOAL, bold: true, margin: 0,
  });
  slide.addShape(pres.shapes.OVAL, {
    x: 0.55, y: 1.06, w: 0.10, h: 0.10,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });
}

function addBullets(slide, bullets, opts = {}) {
  const x = opts.x || 0.55;
  const y = opts.y || 1.40;
  const w = opts.w || 4.6;
  const h = opts.h || 3.5;
  const fontSize = opts.fontSize || 16;
  const paraSpaceAfter = opts.paraSpaceAfter || 6;
  const items = bullets.map((b, i) => ({
    text: b,
    options: { bullet: { code: "25CF" }, breakLine: i < bullets.length - 1, paraSpaceAfter },
  }));
  slide.addText(items, {
    x, y, w, h,
    fontSize, fontFace: FONT_BODY, color: C.CHARCOAL,
    valign: "top", margin: 0,
  });
}

// ============================================================================
// SLIDE 1 — Title
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_DARK };

  s.addShape(pres.shapes.RECTANGLE, {
    x: W - 0.6, y: 0, w: 0.6, h: H,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 2.5, w: 1.5, h: 0.04,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });

  s.addText("Chasing Pavements", {
    x: 0.7, y: 1.4, w: 8.0, h: 1.0,
    fontSize: 56, fontFace: FONT_HEAD, color: C.WHITE, bold: true, margin: 0,
  });
  s.addText("The Welfare Cost of Unpaved Roads in Sub-Saharan Africa", {
    x: 0.7, y: 2.65, w: 8.0, h: 0.6,
    fontSize: 22, fontFace: FONT_HEAD, color: "CADCFC", italic: true, margin: 0,
  });

  s.addText("Olalekan Bello", {
    x: 0.7, y: 4.30, w: 6.5, h: 0.4,
    fontSize: 18, fontFace: FONT_BODY, color: C.WHITE, bold: true, margin: 0,
  });
  s.addText("NYU Africa House Fellowship  ·  Progress Report, April 2026", {
    x: 0.7, y: 4.75, w: 8.0, h: 0.3,
    fontSize: 13, fontFace: FONT_BODY, color: "CADCFC", margin: 0,
  });
}

// ============================================================================
// SLIDE 2 — The Hook (stark photos)
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);

  s.addText("Fewer than 1 in 6 roads in", {
    x: 0.55, y: 0.30, w: 9.0, h: 0.45,
    fontSize: 22, fontFace: FONT_HEAD, color: C.CHARCOAL, margin: 0,
  });
  s.addText("Sub-Saharan Africa are paved.", {
    x: 0.55, y: 0.82, w: 9.0, h: 0.65,
    fontSize: 32, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });

  const photoY = 1.65;
  const photoH = 2.85;
  const ugW = photoH * (1734 / 1301);
  const knW = photoH * (2992 / 2000);

  s.addImage({
    path: FIG("unpaved_road_uganda.jpg"),
    x: 0.55, y: photoY, w: ugW, h: photoH,
    sizing: { type: "cover", w: ugW, h: photoH },
  });
  s.addImage({
    path: FIG("unpaved_road_kenya.jpg"),
    x: 0.55 + ugW + 0.20, y: photoY, w: knW, h: photoH,
    sizing: { type: "cover", w: knW, h: photoH },
  });

  s.addText("This is what a road looks like in much of the continent — even \"paved on the map\" often isn't.", {
    x: 0.55, y: 4.62, w: W - 1.0, h: 0.30,
    fontSize: 13, fontFace: FONT_BODY, color: C.CHARCOAL, italic: true, margin: 0,
  });
  s.addText("Photos: Y. Coetsee, Southern Uganda 2013 (CC BY-SA 4.0); T. Brooks, Kenya 2020 (CC BY-SA 4.0). Wikimedia Commons.", {
    x: 0.55, y: 4.94, w: W - 1.0, h: 0.20,
    fontSize: 8, fontFace: FONT_BODY, color: C.MUTED, italic: true, margin: 0,
  });

  addFooter(s, 2);
}

// ============================================================================
// SLIDE 3 — Why this is a network problem
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Roads aren't projects — they're a network.");

  addBullets(s, [
    "Cost-benefit studies evaluate one road at a time.",
    "But a new road in one district changes prices five districts away.",
    "It moves where things are produced and where workers live.",
    "We need a tool that captures the whole network at once.",
  ], { x: 0.55, y: 1.40, w: 4.4, h: 3.5, fontSize: 16 });

  const imgH = 3.4;
  const imgW = imgH * (1163 / 884);
  s.addImage({
    path: FIG("schematic_network.png"),
    x: W - imgW - 0.5, y: 1.30, w: imgW, h: imgH,
  });

  addFooter(s, 3);
}

// ============================================================================
// SLIDE 4 — How spatial trade models think about this
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "How the model thinks about a road.");

  addBullets(s, [
    "A road change forces three things to adjust at once:",
    "  · what people pay (transport costs in every imported good)",
    "  · what regions produce (cheaper inputs attract activity)",
    "  · where people live (workers move toward better opportunities)",
    "The model lets all three shift until the economy settles.",
    "That feedback is what one-road cost-benefit studies miss.",
  ], { x: 0.55, y: 1.40, w: 4.5, h: 3.5, fontSize: 14 });

  const imgH = 3.4;
  const imgW = imgH * (1197 / 809);
  s.addImage({
    path: FIG("schematic_method_loop.png"),
    x: W - imgW - 0.4, y: 1.30, w: imgW, h: imgH,
  });

  addFooter(s, 4);
}

// ============================================================================
// SLIDE 5 — NEW: Walk through one road change
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Walk through one road change.");

  // 5 numbered horizontal steps as cards
  const steps = [
    { n: "1", title: "A road is paved",        body: "An unpaved trunk segment becomes paved." },
    { n: "2", title: "Trade costs fall",       body: "Moving goods along it gets ~30% cheaper." },
    { n: "3", title: "Prices drop nearby",     body: "Imported food and inputs get cheaper for inland districts. Real wages rise." },
    { n: "4", title: "People & firms move",    body: "Some firms relocate toward cheaper inputs; some workers move toward better jobs." },
    { n: "5", title: "A new equilibrium",      body: "Prices, production, and population settle into a new pattern." },
  ];

  const cardW = 1.78;
  const cardH = 2.95;
  const startX = 0.55;
  const gapX = 0.10;
  const cardY = 1.30;

  steps.forEach((step, i) => {
    const x = startX + i * (cardW + gapX);

    // Card background
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: C.WHITE }, line: { color: "DDDDDD", width: 1 },
      shadow: { type: "outer", color: "000000", blur: 6, offset: 1, angle: 90, opacity: 0.08 },
    });

    // Number circle
    s.addShape(pres.shapes.OVAL, {
      x: x + cardW/2 - 0.30, y: cardY + 0.20, w: 0.60, h: 0.60,
      fill: { color: C.TERRACOTTA }, line: { type: "none" },
    });
    s.addText(step.n, {
      x: x + cardW/2 - 0.30, y: cardY + 0.20, w: 0.60, h: 0.60,
      fontSize: 26, fontFace: FONT_HEAD, color: C.WHITE, bold: true,
      align: "center", valign: "middle", margin: 0,
    });

    // Title
    s.addText(step.title, {
      x: x + 0.10, y: cardY + 0.95, w: cardW - 0.20, h: 0.5,
      fontSize: 13, fontFace: FONT_HEAD, color: C.CHARCOAL, bold: true,
      align: "center", margin: 0,
    });

    // Body
    s.addText(step.body, {
      x: x + 0.12, y: cardY + 1.45, w: cardW - 0.24, h: cardH - 1.55,
      fontSize: 10, fontFace: FONT_BODY, color: C.CHARCOAL,
      align: "center", valign: "top", margin: 0,
    });
  });

  // Footer takeaway
  s.addText(
    "Every road in the country moves through this loop simultaneously — and the model finds the point where everything balances.",
    {
      x: 0.55, y: 4.45, w: W - 1.0, h: 0.55,
      fontSize: 12, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true,
      align: "center", valign: "middle", margin: 0,
    }
  );

  addFooter(s, 5);
}

// ============================================================================
// SLIDE 6 — The data
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "The data: every road on the continent.");

  addBullets(s, [
    "OpenStreetMap (OSM): millions of road segments tagged with surface type — paved, unpaved, or unknown.",
    "Cross-checked against an independent satellite-derived ML dataset (Liu et al. 2026).",
    "Road-level agreement: 93.7%. The two sources tell the same story.",
    "OSM is conservative — it understates paving, so our welfare estimates lean conservative too.",
  ], { x: 0.55, y: 1.40, w: 4.5, h: 3.5, fontSize: 15 });

  const imgW = 4.6;
  const imgH = imgW / (1783 / 883);
  s.addImage({
    path: FIG("tanzania_surface_coverage.png"),
    x: W - imgW - 0.4, y: 1.50, w: imgW, h: imgH,
  });

  s.addText("Example: Tanzania surface coverage. 2.2% paved, 66.5% unpaved, 31.3% unknown.", {
    x: W - imgW - 0.4, y: 1.50 + imgH + 0.05, w: imgW, h: 0.30,
    fontSize: 10, fontFace: FONT_BODY, color: C.MUTED, italic: true, align: "center", margin: 0,
  });

  addFooter(s, 6);
}

// ============================================================================
// SLIDE 7 — What "welfare gain" means here (cleaned per user feedback)
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "What \"welfare gain\" means here.");

  addBullets(s, [
    "We measure real income — what wages actually buy.",
    "Gains come from lower prices, not bigger paychecks.",
    "Bad roads act like a hidden tax on remote communities: everything imported costs more.",
    "Pave the network → prices fall → the same wage stretches further.",
  ], { x: 0.55, y: 1.40, w: 5.0, h: 3.5, fontSize: 16 });

  // Right-side visual: a clean equation card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.0, y: 1.50, w: 3.6, h: 3.0,
    fill: { color: C.CALLOUT_BG }, line: { color: C.TERRACOTTA, width: 1 },
  });
  s.addText("real income  =", {
    x: 6.15, y: 1.75, w: 3.4, h: 0.5,
    fontSize: 18, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true,
    align: "center", margin: 0,
  });
  s.addText("wages", {
    x: 6.15, y: 2.30, w: 3.4, h: 0.45,
    fontSize: 22, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true,
    align: "center", margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.6, y: 2.85, w: 2.4, h: 0.025,
    fill: { color: C.CHARCOAL }, line: { type: "none" },
  });
  s.addText("price level", {
    x: 6.15, y: 2.95, w: 3.4, h: 0.45,
    fontSize: 22, fontFace: FONT_HEAD, color: C.SLATE, bold: true,
    align: "center", margin: 0,
  });
  s.addText("Paving lowers the denominator.", {
    x: 6.15, y: 3.75, w: 3.4, h: 0.5,
    fontSize: 13, fontFace: FONT_BODY, color: C.CHARCOAL,
    align: "center", italic: true, margin: 0,
  });

  addFooter(s, 7);
}

// ============================================================================
// SLIDE 8 — Pipeline coverage
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "One pipeline, 41 countries.");

  addBullets(s, [
    "Same data sources, same method, every country.",
    "End-to-end automated: download OSM, build network, simulate counterfactual, store results.",
    "41 mainland Sub-Saharan African countries completed.",
    "Excluded: 7 island nations, 2 with missing GDP data.",
  ], { x: 0.55, y: 1.40, w: 5.0, h: 3.5, fontSize: 15 });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.0, y: 1.50, w: 3.6, h: 1.5,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });
  s.addText("41", {
    x: 6.0, y: 1.55, w: 3.6, h: 1.0,
    fontSize: 84, fontFace: FONT_HEAD, color: C.WHITE, bold: true, align: "center", margin: 0,
  });
  s.addText("countries, end-to-end", {
    x: 6.0, y: 2.55, w: 3.6, h: 0.4,
    fontSize: 14, fontFace: FONT_BODY, color: C.WHITE, align: "center", margin: 0,
  });

  const imgW = 3.6;
  const imgH = imgW / 2.02;
  s.addImage({
    path: FIG("tanzania_surface_by_class.png"),
    x: 6.0, y: 3.20, w: imgW, h: imgH,
  });
  s.addText("By road class — Tanzania example.", {
    x: 6.0, y: 3.20 + imgH + 0.02, w: imgW, h: 0.25,
    fontSize: 9, fontFace: FONT_BODY, color: C.MUTED, italic: true, align: "center", margin: 0,
  });

  addFooter(s, 8);
}

// ============================================================================
// SLIDE 9 — Headline number
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Paving every road would raise real incomes by ~9%.");

  s.addText("+8.9%", {
    x: 0.55, y: 1.50, w: 4.0, h: 1.5,
    fontSize: 90, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });
  s.addText("continental average gain in real income", {
    x: 0.55, y: 2.95, w: 4.5, h: 0.4,
    fontSize: 14, fontFace: FONT_BODY, color: C.CHARCOAL, margin: 0,
  });
  s.addText("(population-weighted across 39 countries)", {
    x: 0.55, y: 3.25, w: 4.5, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, color: C.MUTED, italic: true, margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 3.65, w: 4.5, h: 1.20,
    fill: { color: C.CALLOUT_BG }, line: { type: "none" },
  });
  s.addText([
    { text: "Range across 39 countries:", options: { fontSize: 12, color: C.MUTED, breakLine: true } },
    { text: "+1.6%  ", options: { fontSize: 22, bold: true, color: C.SLATE } },
    { text: "(South Africa)   →   ", options: { fontSize: 12, color: C.MUTED } },
    { text: "+16.9%  ", options: { fontSize: 22, bold: true, color: C.TERRACOTTA } },
    { text: "(Somalia)", options: { fontSize: 12, color: C.MUTED } },
  ], {
    x: 0.75, y: 3.75, w: 4.2, h: 1.0,
    fontFace: FONT_BODY, valign: "top", margin: 0,
  });

  const imgH = 4.0;
  const imgW = imgH * (1334 / 1635);
  s.addImage({
    path: FIG("ssa_41_country_welfare.png"),
    x: W - imgW - 0.5, y: 0.95, w: imgW, h: imgH,
  });

  addFooter(s, 9);
}

// ============================================================================
// SLIDE 10 — What does +9% mean in dollars?
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "What does +9% actually mean?");

  // Three big stat blocks across the slide
  const blocks = [
    {
      big:    "$180 B",
      small:  "per year, perpetual",
      note:   "Aggregate real income gain across the 39-country sample, applied to current GDP.",
      color:  C.TERRACOTTA,
    },
    {
      big:    "~$150",
      small:  "per person per year",
      note:   "Continental-average increase in purchasing power for every resident.",
      color:  C.SLATE,
    },
    {
      big:    "~3×",
      small:  "annual ODA to SSA",
      note:   "Welfare gain is roughly 3× total annual development assistance to the region (~$50–60 B).",
      color:  C.SAGE,
    },
  ];

  const blockW = 2.92;
  const blockH = 2.55;
  const startX = 0.55;
  const gapX = 0.10;
  const blockY = 1.30;

  blocks.forEach((blk, i) => {
    const x = startX + i * (blockW + gapX);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: blockY, w: blockW, h: blockH,
      fill: { color: C.WHITE }, line: { color: "DDDDDD", width: 1 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: blockY, w: blockW, h: 0.10,
      fill: { color: blk.color }, line: { type: "none" },
    });
    s.addText(blk.big, {
      x: x + 0.10, y: blockY + 0.30, w: blockW - 0.20, h: 0.95,
      fontSize: 44, fontFace: FONT_HEAD, color: blk.color, bold: true,
      align: "center", valign: "middle", margin: 0,
    });
    s.addText(blk.small, {
      x: x + 0.10, y: blockY + 1.30, w: blockW - 0.20, h: 0.30,
      fontSize: 11, fontFace: FONT_BODY, color: C.CHARCOAL, bold: true,
      align: "center", margin: 0,
    });
    s.addText(blk.note, {
      x: x + 0.15, y: blockY + 1.70, w: blockW - 0.30, h: blockH - 1.80,
      fontSize: 10, fontFace: FONT_BODY, color: C.MUTED,
      align: "center", valign: "top", margin: 0,
    });
  });

  // Caveat below
  s.addText(
    "Back-of-envelope: applies the +8.9% real income gain to current SSA GDP (~$2T) and population (~1.2B).",
    {
      x: 0.55, y: 4.10, w: W - 1.0, h: 0.30,
      fontSize: 11, fontFace: FONT_BODY, color: C.MUTED, italic: true,
      align: "center", margin: 0,
    }
  );
  s.addText(
    "Once roads are paved, the gain accrues every year — forever, less maintenance.",
    {
      x: 0.55, y: 4.45, w: W - 1.0, h: 0.4,
      fontSize: 13, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true,
      align: "center", margin: 0,
    }
  );

  addFooter(s, 10);
}

// ============================================================================
// SLIDE 11 — Continental map
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Where the gains concentrate.");

  const imgH = 3.9;
  const imgW = imgH * (1216 / 1445);
  s.addImage({
    path: FIG("ssa_welfare_map.png"),
    x: 0.55, y: 1.20, w: imgW, h: imgH,
  });

  addBullets(s, [
    "Highest gains where roads are worst and distances longest.",
    "Lowest where the network is already mature.",
    "Gains visibly cluster in the Sahel, the Horn, and central Africa.",
    "The pattern is not subtle — it follows known geography of infrastructure.",
  ], { x: imgW + 1.0, y: 1.4, w: W - imgW - 1.5, h: 3.5, fontSize: 14 });

  addFooter(s, 11);
}

// ============================================================================
// SLIDE 12 — The ranking lines up (intuition slide; "model wasn't told" line removed)
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "The ranking lines up with what we'd expect.");

  addBullets(s, [
    "The countries with the smallest gains — South Africa, Botswana, Senegal — are the ones with reputations for well-built road networks.",
    "The countries with the largest gains — Somalia, Burundi, Central African Republic, DRC — are where conflict, poverty, and remoteness have left infrastructure thinnest.",
  ], { x: 0.55, y: 1.40, w: 4.6, h: 3.0, fontSize: 14 });

  // Bottom 3 box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.6, y: 1.40, w: 3.9, h: 1.55,
    fill: { color: C.CALLOUT_BG }, line: { color: C.SLATE, width: 1 },
  });
  s.addText("Lowest welfare gain", {
    x: 5.75, y: 1.50, w: 3.7, h: 0.30,
    fontSize: 11, fontFace: FONT_HEAD, color: C.SLATE, bold: true, margin: 0,
  });
  s.addText([
    { text: "South Africa  ", options: {} },{ text: "+1.6%", options: { color: C.SLATE, bold: true, breakLine: true } },
    { text: "Gambia        ", options: {} },{ text: "+2.8%", options: { color: C.SLATE, bold: true, breakLine: true } },
    { text: "Botswana      ", options: {} },{ text: "+3.9%", options: { color: C.SLATE, bold: true } },
  ], {
    x: 5.75, y: 1.85, w: 3.7, h: 1.05,
    fontSize: 14, fontFace: "Consolas", color: C.CHARCOAL, valign: "top", margin: 0,
  });

  // Top 3 box
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.6, y: 3.10, w: 3.9, h: 1.55,
    fill: { color: C.CALLOUT_BG }, line: { color: C.TERRACOTTA, width: 1 },
  });
  s.addText("Highest welfare gain", {
    x: 5.75, y: 3.20, w: 3.7, h: 0.30,
    fontSize: 11, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });
  s.addText([
    { text: "Somalia       ", options: {} },{ text: "+16.9%", options: { color: C.TERRACOTTA, bold: true, breakLine: true } },
    { text: "Burundi       ", options: {} },{ text: "+15.5%", options: { color: C.TERRACOTTA, bold: true, breakLine: true } },
    { text: "CAR           ", options: {} },{ text: "+13.8%", options: { color: C.TERRACOTTA, bold: true } },
  ], {
    x: 5.75, y: 3.55, w: 3.7, h: 1.05,
    fontSize: 14, fontFace: "Consolas", color: C.CHARCOAL, valign: "top", margin: 0,
  });

  s.addText("That match between independent intuition and model output is reassuring.", {
    x: 0.55, y: 4.80, w: W - 1.0, h: 0.35,
    fontSize: 13, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true, align: "center", margin: 0,
  });

  addFooter(s, 12);
}

// ============================================================================
// SLIDE 13 — Why Tanzania
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Zoom in: Tanzania.");

  addBullets(s, [
    "Mid-range gain country — useful for showing a representative case.",
    "Rich sub-national data: 158 districts mapped to OSM road network.",
    "70% of district pairs are connected through the road network today.",
    "Detailed enough to validate, granular enough to ask redistribution questions.",
  ], { x: 0.55, y: 1.40, w: 4.4, h: 3.5, fontSize: 15 });

  const imgH = 3.6;
  const imgW = imgH * (1678 / 1450);
  s.addImage({
    path: FIG("tanzania_connectivity_map.png"),
    x: W - imgW - 0.4, y: 1.30, w: imgW, h: imgH,
  });

  addFooter(s, 13);
}

// ============================================================================
// SLIDE 14 — Where trade gets cheaper
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Where trade gets cheaper.");

  const imgH = 3.9;
  const imgW = imgH * (1665 / 1450);
  s.addImage({
    path: FIG("tanzania_trade_cost_reduction_map.png"),
    x: 0.55, y: 1.20, w: imgW, h: imgH,
  });

  addBullets(s, [
    "Paving the network cuts trade costs most for inland, off-trunk districts.",
    "These are the communities currently paying the steepest \"distance tax.\"",
    "Average iceberg-cost reduction across district pairs: 23%.",
    "Range: 0% to 55%.",
  ], { x: imgW + 1.0, y: 1.40, w: W - imgW - 1.5, h: 3.5, fontSize: 14 });

  addFooter(s, 14);
}

// ============================================================================
// SLIDE 15 — Winners and losers within a country
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Where do the gains land within a country?");

  addBullets(s, [
    "Headline gain is national; the story underneath is reallocation.",
    "Remote inland districts (Nyang'hwale, Pangani, Mkalama) gain +18-22% under realistic mobility frictions and attract +16-26% in-migration.",
    "Lake Victoria's Ukerewe and Zanzibar/Pemba islands gain only +2-3%: they're disconnected from mainland paving. Residents move toward better-connected districts (-12% population each).",
    "Net effect: paving redirects people toward newly cheaper-to-reach mainland markets.",
  ], { x: 0.55, y: 1.40, w: 4.5, h: 3.5, fontSize: 13 });

  const imgW = 4.6;
  const imgH = imgW / (1400 / 700);
  s.addImage({
    path: FIG("tanzania_district_rankings.png"),
    x: W - imgW - 0.4, y: 1.40, w: imgW, h: imgH,
  });
  s.addText("Tanzania districts under frictional mobility (κ=2).", {
    x: W - imgW - 0.4, y: 1.40 + imgH + 0.05, w: imgW, h: 0.25,
    fontSize: 9, fontFace: FONT_BODY, color: C.MUTED, italic: true, align: "center", margin: 0,
  });

  addFooter(s, 15);
}

// ============================================================================
// SLIDE 16 — Google Maps validation (technical bullet removed)
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Ground-truthing with Google Maps.");

  addBullets(s, [
    "Picked 16 random Tanzanian road segments — 8 paved, 8 unpaved.",
    "Compared the resulting travel speeds.",
    "Paved roads are 1.22× faster on equivalent terrain.",
    "The speed gap our cost model assumes is anchored in real travel times.",
  ], { x: 0.55, y: 1.30, w: 4.3, h: 3.6, fontSize: 14 });

  const imgH = 3.5;
  const imgW = imgH * (1110 / 735);
  const finalW = Math.min(imgW, 4.7);
  const finalH = finalW / (1110 / 735);
  s.addImage({
    path: FIG("gmaps_speed_comparison.png"),
    x: W - finalW - 0.4, y: 1.30, w: finalW, h: finalH,
  });

  addFooter(s, 16);
}

// ============================================================================
// SLIDE 17 — NEW: Multi-country GMaps validation
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "And the gap holds across countries.");

  addBullets(s, [
    "Repeated the test in Kenya: same method, fresh segments.",
    "Paved roads are 1.58× faster — even bigger gap than Tanzania.",
    "2 of 16 unpaved Kenya routes returned \"no route\" — Google can't always find a way through.",
    "Pooled across both countries (30 valid queries): paved is 1.35× faster.",
  ], { x: 0.55, y: 1.30, w: 4.3, h: 3.6, fontSize: 13, paraSpaceAfter: 8 });

  // Two-country figure (1100 x 500 ratio = 2.2)
  const imgW = 4.7;
  const imgH = imgW / 2.2;
  s.addImage({
    path: FIG("gmaps_speed_two_country.png"),
    x: W - imgW - 0.4, y: 1.80, w: imgW, h: imgH,
  });

  addFooter(s, 17);
}

// ============================================================================
// SLIDE 18 — Why this beats project-by-project (improved spacing)
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Why our numbers are larger than typical road studies.");

  // Two-column layout: "What CBA captures" vs "What CBA misses"
  // Left card: captures
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 1.40, w: 4.4, h: 3.3,
    fill: { color: C.WHITE }, line: { color: "DDDDDD", width: 1 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 1.40, w: 4.4, h: 0.10,
    fill: { color: C.SLATE }, line: { type: "none" },
  });
  s.addText("Standard cost-benefit captures", {
    x: 0.70, y: 1.60, w: 4.1, h: 0.4,
    fontSize: 14, fontFace: FONT_HEAD, color: C.SLATE, bold: true, margin: 0,
  });
  addBullets(s, [
    "Truck-time savings on the road being built.",
    "Slightly cheaper goods at the immediate endpoints.",
    "A few jobs created during construction.",
  ], { x: 0.70, y: 2.10, w: 4.1, h: 2.5, fontSize: 13, paraSpaceAfter: 14 });

  // Right card: misses
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.05, y: 1.40, w: 4.4, h: 3.3,
    fill: { color: C.WHITE }, line: { color: "DDDDDD", width: 1 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.05, y: 1.40, w: 4.4, h: 0.10,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });
  s.addText("Standard cost-benefit misses", {
    x: 5.20, y: 1.60, w: 4.1, h: 0.4,
    fontSize: 14, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });
  addBullets(s, [
    "Expanded market access for newly connected communities.",
    "Cheaper imports and wider product variety.",
    "Workers moving toward better-paying regions.",
    "Firms relocating to take advantage of lower costs.",
  ], { x: 5.20, y: 2.10, w: 4.1, h: 2.5, fontSize: 13, paraSpaceAfter: 14 });

  // Bottom line
  s.addText(
    "Network effects are where most of the welfare gain lives. One-road studies systematically undercount.",
    {
      x: 0.55, y: 4.85, w: W - 1.0, h: 0.40,
      fontSize: 13, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true,
      align: "center", margin: 0,
    }
  );

  addFooter(s, 18);
}

// ============================================================================
// SLIDE 19 — NEW: Limitations
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "What this analysis doesn't capture.");

  addBullets(s, [
    "Maintenance: paved roads need upkeep that unpaved often skip.",
    "Construction time: gains take years to materialize, not days.",
    "Congestion: better roads attract more traffic, which can offset some gains.",
    "Environmental costs: paving has carbon and habitat impacts not in our welfare measure.",
    "Wet vs. dry season: an unpaved road is two different roads across the year.",
    "Substitutes: rail, river, and air transport reshape what roads are worth.",
  ], { x: 0.55, y: 1.30, w: W - 1.0, h: 3.2, fontSize: 14, paraSpaceAfter: 10 });

  // Closing line
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.55, y: 4.55, w: W - 1.0, h: 0.55,
    fill: { color: C.CALLOUT_BG }, line: { type: "none" },
  });
  s.addText(
    "These are exactly the reasons the next steps focus on optimal paving and seasonal robustness rather than \"pave everything.\"",
    {
      x: 0.65, y: 4.60, w: W - 1.2, h: 0.45,
      fontSize: 12, fontFace: FONT_HEAD, color: C.CHARCOAL, italic: true,
      align: "center", valign: "middle", margin: 0,
    }
  );

  addFooter(s, 19);
}

// ============================================================================
// SLIDE 20 — Optimal paving on a budget
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_LIGHT };
  addAccentBar(s);
  addTitle(s, "Next: optimal paving on a budget.");

  addBullets(s, [
    "Most ministries can't pave everything. They pave something.",
    "Extend the model to rank each road segment by gain-per-dollar of paving cost.",
    "Output: a priority list a transport ministry can actually act on.",
    "Lets us answer: \"with $X, where do you get the most welfare?\"",
  ], { x: 0.55, y: 1.40, w: 4.6, h: 3.5, fontSize: 15 });

  const imgH = 3.4;
  const imgW = imgH * (1078 / 809);
  s.addImage({
    path: FIG("schematic_priority.png"),
    x: W - imgW - 0.4, y: 1.30, w: imgW, h: imgH,
  });

  addFooter(s, 20);
}

// ============================================================================
// SLIDE 21 — Thank you / Closing
// ============================================================================
{
  let s = pres.addSlide();
  s.background = { color: C.BG_DARK };

  s.addShape(pres.shapes.RECTANGLE, {
    x: W - 0.6, y: 0, w: 0.6, h: H,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 1.10, w: 1.5, h: 0.04,
    fill: { color: C.TERRACOTTA }, line: { type: "none" },
  });

  s.addText("Thank you.", {
    x: 0.7, y: 0.45, w: 8.0, h: 0.7,
    fontSize: 44, fontFace: FONT_HEAD, color: C.WHITE, bold: true, margin: 0,
  });

  const imgH = 3.0;
  const imgW = imgH * (1216 / 1445);
  s.addImage({
    path: FIG("ssa_welfare_map.png"),
    x: 0.7, y: 1.50, w: imgW, h: imgH,
  });

  const tx = imgW + 1.2;
  const tw = W - tx - 1.0;

  s.addText("Timeline", {
    x: tx, y: 1.50, w: tw, h: 0.35,
    fontSize: 14, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });
  s.addText([
    { text: "·  Working paper draft by end of summer 2026", options: { breakLine: true, paraSpaceAfter: 6 } },
    { text: "·  Replication code public; pipeline reusable across SSA", options: { breakLine: true, paraSpaceAfter: 6 } },
    { text: "·  Optimal-paving extension underway", options: {} },
  ], {
    x: tx, y: 1.85, w: tw, h: 1.2,
    fontSize: 12, fontFace: FONT_BODY, color: "CADCFC", valign: "top", margin: 0,
  });

  s.addText("With thanks", {
    x: tx, y: 3.20, w: tw, h: 0.35,
    fontSize: 14, fontFace: FONT_HEAD, color: C.TERRACOTTA, bold: true, margin: 0,
  });
  s.addText("The NYU Africa House Fellowship made the continental scope of this project possible.", {
    x: tx, y: 3.55, w: tw, h: 0.9,
    fontSize: 12, fontFace: FONT_BODY, color: "CADCFC", italic: true, valign: "top", margin: 0,
  });

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: H - 0.85, w: W - 1.4, h: 0.025,
    fill: { color: C.TERRACOTTA, transparency: 50 }, line: { type: "none" },
  });
  s.addText("Olalekan Bello  ·  ob708@nyu.edu  ·  NYU", {
    x: 0.7, y: H - 0.70, w: W - 1.4, h: 0.4,
    fontSize: 13, fontFace: FONT_BODY, color: C.WHITE, margin: 0,
  });
}

// ---------- Save ----------
pres.writeFile({ fileName: "chasing_pavements_fellowship_report.pptx" })
  .then((fileName) => console.log("Wrote: " + fileName))
  .catch((err) => { console.error(err); process.exit(1); });
