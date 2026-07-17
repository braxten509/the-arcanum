/* Pure course-control fallback used when a live server has an older map reader loaded. */
export function fallbackCourseControl(manifest, status) {
  const sections = Array.isArray(manifest?.sections) ? manifest.sections : [];
  if (!sections.length) return null;
  const progress = status?.sectionProgress || {};
  const currentIndex = Math.max(1, Number(progress.index) || 1);
  const currentSection = progress.section || sections[currentIndex - 1]?.id || sections[0]?.id;
  return {
    fallback: true, currentIndex, currentSection, blockers: [],
    spine: sections.map((section, index) => {
      const statusName = index + 1 < currentIndex ? "verified"
        : section.id === currentSection ? "current" : "planned";
      return { id: section.id, title: section.title || section.short || section.id,
        milestone: section.build || "", status: statusName,
        mark: statusName === "verified" ? "✓" : statusName === "current" ? "▶" : "○",
        statusLabel: statusName };
    }),
  };
}
