(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const revealItems = [...document.querySelectorAll("[data-reveal]")];

  document.documentElement.classList.add("motion-ready");

  if (reducedMotion || !("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  } else {
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) {
          window.setTimeout(() => entry.target.classList.add("is-visible"), 70);
          observer.unobserve(entry.target);
        }
      }),
      { threshold: 0.08 },
    );
    revealItems.forEach((item) => {
      const bounds = item.getBoundingClientRect();
      if (bounds.top < window.innerHeight && bounds.bottom > 0) {
        item.classList.add("is-visible");
      } else {
        observer.observe(item);
      }
    });
  }

  document.querySelectorAll("[data-evidence-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const id = link.getAttribute("href");
      const target = id ? document.querySelector(id) : null;
      if (!target) return;

      event.preventDefault();
      target.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
      target.classList.remove("evidence-focus");
      window.requestAnimationFrame(() => target.classList.add("evidence-focus"));
      window.setTimeout(() => target.classList.remove("evidence-focus"), 1200);
      history.replaceState(null, "", id);
    });
  });

  document.querySelectorAll("[data-action-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button");
      if (!button) return;
      form.classList.add("form-pending");
      button.disabled = true;
      button.textContent = button.classList.contains("secondary") ? "Restoring..." : "Applying...";
    });
  });

  document.querySelectorAll(".angle").forEach((angle) => {
    angle.addEventListener("click", () => {
      document.querySelectorAll(".angle").forEach((item) => {
        item.classList.remove("active");
        item.setAttribute("aria-pressed", "false");
      });
      angle.classList.add("active");
      angle.setAttribute("aria-pressed", "true");
    });
  });
})();
