// Intersection Observer for scroll-triggered fade-in animations
const observerOptions = {
  root: null,
  rootMargin: '0px',
  threshold: 0.15
};

const observer = new IntersectionObserver((entries, observer) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    }
  });
}, observerOptions);

document.addEventListener('DOMContentLoaded', () => {
  const animatedSections = document.querySelectorAll('.scroll-anim');
  animatedSections.forEach(section => {
    observer.observe(section);
  });

  // Terminal ticker effect in Hero section
  const tickerTextElement = document.querySelector('.ticker-text');
  if (tickerTextElement) {
    const messages = [
      "> Reading documentation...",
      "> Extracting endpoints...",
      "> Generating models...",
      "> Running live tests...",
      "> SDK generated successfully."
    ];
    let messageIndex = 0;
    let charIndex = 0;
    let isDeleting = false;
    let typingSpeed = 50;

    function typeTicker() {
      const currentMessage = messages[messageIndex];

      if (isDeleting) {
        tickerTextElement.textContent = currentMessage.substring(0, charIndex - 1);
        charIndex--;
        typingSpeed = 30; // Faster deleting
      } else {
        tickerTextElement.textContent = currentMessage.substring(0, charIndex + 1);
        charIndex++;
        typingSpeed = Math.random() * 50 + 50; // Variable typing speed
      }

      if (!isDeleting && charIndex === currentMessage.length) {
        // Pause at end of word
        typingSpeed = 2000;
        isDeleting = true;
      } else if (isDeleting && charIndex === 0) {
        isDeleting = false;
        messageIndex = (messageIndex + 1) % messages.length;
        typingSpeed = 500; // Pause before typing next word
      }

      setTimeout(typeTicker, typingSpeed);
    }

    // Start typing effect after a short delay
    setTimeout(typeTicker, 1000);
  }
});
