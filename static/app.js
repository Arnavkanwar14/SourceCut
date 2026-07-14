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
      const player = document.querySelector("[data-source-player]");
      const time = Number(link.dataset.seek);
      if (player && Number.isFinite(time)) {
        player.currentTime = time;
        player.play().catch(() => {});
      }
      history.replaceState(null, "", id);
    });
  });

  document.querySelectorAll("[data-seek]").forEach((control) => {
    if (control.matches("[data-evidence-link]")) return;
    control.addEventListener("click", () => {
      const player = document.querySelector("[data-source-player]");
      const time = Number(control.dataset.seek);
      if (!player || !Number.isFinite(time)) return;
      player.currentTime = time;
      player.play().catch(() => {});
    });
  });

  document.querySelectorAll("[data-action-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button");
      if (!button) return;
      form.classList.add("form-pending");
      button.disabled = true;
      button.textContent = button.classList.contains("secondary") ? "Updating..." : "Applying...";
    });
  });

  document.querySelectorAll("[data-delete-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Delete this project and its rendered outputs? This cannot be undone.")) {
        event.preventDefault();
      }
    });
  });

  const productionForm = document.querySelector("[data-production-form]");
  if (productionForm) {
    const file = productionForm.querySelector("[data-source-file]");
    const fileName = productionForm.querySelector("[data-file-name]");
    const message = productionForm.querySelector(".form-message");
    const fileDrop = productionForm.querySelector("[data-file-drop]");
    const audioMode = productionForm.querySelector("[data-audio-mode]");
    const voiceField = productionForm.querySelector("[data-voice-field]");
    const voice = voiceField?.querySelector("select");
    const setVoiceState = () => {
      const useVoiceover = audioMode?.value === "voiceover";
      if (voice) voice.disabled = !useVoiceover;
      voiceField?.classList.toggle("is-muted", !useVoiceover);
    };
    audioMode?.addEventListener("change", setVoiceState);
    setVoiceState();
    file?.addEventListener("change", () => {
      const picked = file.files?.[0];
      const extension = picked?.name.split(".").pop()?.toLowerCase() || "";
      const supported = ["mp4", "mp3", "wav"].includes(extension);
      const tooLarge = Boolean(picked && picked.size > 500 * 1024 * 1024);
      const error = tooLarge ? "Choose a file no larger than 500 MB." : (!supported ? "Choose an MP4, MP3, or WAV file." : "");
      file.setCustomValidity(error);
      fileDrop?.classList.toggle("has-file", Boolean(picked && !error));
      fileDrop?.classList.toggle("invalid", Boolean(error));
      if (fileName) fileName.textContent = error || (picked ? `${picked.name} - ${(picked.size / 1024 / 1024).toFixed(1)} MB ready for analysis` : "MP4, MP3, or WAV up to 500 MB.");
    });
    productionForm.addEventListener("submit", () => {
      const button = productionForm.querySelector("button");
      if (button) {
        button.disabled = true;
        button.textContent = "Creating project...";
      }
      if (message) message.textContent = "Your source is being stored locally, then SourceCut will open its production desk.";
    });
  }

  const jobPanel = document.querySelector("[data-job-status]");
  if (jobPanel) {
    const endpoint = jobPanel.dataset.jobStatus;
    const detail = jobPanel.querySelector("[data-job-detail]");
    const state = jobPanel.querySelector("[data-job-state]");
    const poll = async () => {
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) return;
        const data = await response.json();
        if (data.job && detail) detail.textContent = data.job.detail || data.job.stage;
        if (data.job && state) state.textContent = data.job.status;
        if (data.job?.status === "done" || data.job?.status === "failed") {
          window.location.reload();
          return;
        }
        window.setTimeout(poll, 1500);
      } catch (_) {
        window.setTimeout(poll, 3000);
      }
    };
    window.setTimeout(poll, 900);
  }

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
