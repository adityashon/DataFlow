  // ── Drag & Drop ────────────────────────────────────────────────────────────
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const form = document.getElementById("uploadForm");
  const progress = document.getElementById("uploadProgress");

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () =>
    dropZone.classList.remove("drag-over"),
  );
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (!file) return;
    // Create a DataTransfer to set the input's files (needed for form submission)
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    submitForm();
  });

  // Auto-submit when file is chosen via the label
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) submitForm();
  });

  function submitForm() {
    progress.classList.add("active");
    form.submit();
  }
