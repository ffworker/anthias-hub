/* Progressive, lazy read-only media thumbnails. No autoplay or mutation. */
(() => {
  'use strict';
  const tiles = document.querySelectorAll('.asset-media-preview, .library-media-preview');
  const videos = [];

  tiles.forEach((tile) => {
    const image = tile.querySelector('img.asset-preview-content');
    if (image) {
      const ready = () => { if (image.naturalWidth > 0) tile.classList.add('preview-ready'); };
      image.addEventListener('load', ready);
      image.addEventListener('error', () => tile.classList.remove('preview-ready'));
      if (image.complete) ready();
    }
    const video = tile.querySelector('video.asset-preview-video');
    if (!video) return;
    video.addEventListener('error', () => {
      tile.classList.remove('preview-ready');
      video.removeAttribute('src');
      video.load();
    }, {once: true});
    const showFrame = () => {
      video.pause();
      if (video.readyState >= 2) tile.classList.add('preview-ready');
    };
    video.addEventListener('loadeddata', showFrame, {once: true});
    video.addEventListener('seeked', showFrame, {once: true});
    video.addEventListener('loadedmetadata', () => {
      // Seeking a little past zero usually paints a representative still,
      // without ever starting the video or downloading it on page load.
      if (Number.isFinite(video.duration) && video.duration > 0.2) {
        try { video.currentTime = Math.min(0.6, video.duration / 2); } catch (_) { /* fallback icon */ }
      }
    }, {once: true});
    videos.push(video);
  });

  const activate = (video) => {
    if (!video.dataset.previewSrc) return;
    video.src = video.dataset.previewSrc;
    video.removeAttribute('data-preview-src');
    video.preload = 'metadata';
    video.load();
  };
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        activate(entry.target);
      });
    }, {rootMargin: '100px'});
    videos.forEach((video) => observer.observe(video));
  } else {
    // Without viewport observation, keep video tiles as icons to avoid
    // downloading an entire playlist's clips.
  }
})();
