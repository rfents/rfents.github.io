import './App.css';
import { useEffect } from 'react';

function App() {
  useEffect(() => {
    // Animate skill bars when they come into view
    const observerOptions = {
      threshold: 0.5,
      rootMargin: '0px 0px -100px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const skillBars = entry.target.querySelectorAll('.skill-progress');
          skillBars.forEach(bar => {
            const width = bar.getAttribute('data-width');
            bar.style.setProperty('--width', width);
            bar.style.width = width;
          });
        }
      });
    }, observerOptions);

    const skillsSection = document.querySelector('.skills');
    if (skillsSection) {
      observer.observe(skillsSection);
    }

    // Smooth scrolling for navigation links
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href');
        const targetSection = document.querySelector(targetId);
        if (targetSection) {
          targetSection.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      });
    });

    // Add scroll effect to navbar
    const navbar = document.querySelector('.navbar');
    const handleScroll = () => {
      if (window.scrollY > 100) {
        navbar.style.background = 'rgba(10, 10, 10, 0.98)';
        navbar.style.boxShadow = '0 2px 20px rgba(139, 92, 246, 0.1)';
      } else {
        navbar.style.background = 'rgba(10, 10, 10, 0.95)';
        navbar.style.boxShadow = 'none';
      }
    };

    window.addEventListener('scroll', handleScroll);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      observer.disconnect();
    };
  }, []);

  const handleButtonClick = (type) => {
    if (type === 'work') {
      document.querySelector('#projects').scrollIntoView({ behavior: 'smooth' });
    } else if (type === 'contact') {
      document.querySelector('#contact').scrollIntoView({ behavior: 'smooth' });
    }
  };
  return (
    <div className="App">
      {/* Navigation */}
      <nav className="navbar">
        <div className="nav-container">
          <div className="nav-logo">
            <span className="logo-text">FDA</span>
          </div>
          <ul className="nav-menu">
            <li><a href="#home" className="nav-link">Home</a></li>
            <li><a href="#about" className="nav-link">About</a></li>
            <li><a href="#skills" className="nav-link">Skills</a></li>
            <li><a href="#projects" className="nav-link">Projects</a></li>
            <li><a href="#contact" className="nav-link">Contact</a></li>
          </ul>
        </div>
      </nav>

      {/* Hero Section */}
      <section id="home" className="hero">
        <div className="hero-background">
          <div className="particles"></div>
        </div>
        <div className="hero-content">
          <h1 className="hero-title">
            <span className="title-line">Fenontsoa D. ANDRIANARIVONDRIAKA</span>
            <span className="title-line highlight">Portfolio</span>
          </h1>
          <p className="hero-subtitle">
            Creating digital experiences that push the boundaries of innovation
          </p>
          <div className="hero-buttons">
            <button className="btn-primary" onClick={() => handleButtonClick('work')}>View My Work</button>
            <button className="btn-secondary" onClick={() => handleButtonClick('contact')}>Get In Touch</button>
          </div>
        </div>
        <div className="scroll-indicator">
          <div className="scroll-arrow"></div>
        </div>
      </section>

      {/* About Section */}
      <section id="about" className="about">
        <div className="container">
          <h2 className="section-title">About Me</h2>
          <div className="about-content">
            <div className="about-text">
              <p>
                Passionate developer with expertise in modern web technologies. 
                I specialize in creating immersive digital experiences that combine 
                cutting-edge design with robust functionality.
              </p>
              <div className="stats">
                <div className="stat-item">
                  <span className="stat-number">50+</span>
                  <span className="stat-label">Projects</span>
                </div>
                <div className="stat-item">
                  <span className="stat-number">3+</span>
                  <span className="stat-label">Years</span>
                </div>
                <div className="stat-item">
                  <span className="stat-number">100%</span>
                  <span className="stat-label">Passion</span>
                </div>
              </div>
            </div>
            <div className="about-image">
              <div className="image-container">
                <div className="image-glow"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Skills Section */}
      <section id="skills" className="skills">
        <div className="container">
          <h2 className="section-title">Skills & Technologies</h2>
          <div className="skills-grid">
            <div className="skill-category">
              <h3>Frontend</h3>
              <div className="skill-items">
                <div className="skill-item">
                  <span>React</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="90%"></div>
                  </div>
                </div>
                <div className="skill-item">
                  <span>JavaScript</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="85%"></div>
                  </div>
                </div>
                <div className="skill-item">
                  <span>CSS3</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="95%"></div>
                  </div>
                </div>
              </div>
            </div>
            <div className="skill-category">
              <h3>Backend</h3>
              <div className="skill-items">
                <div className="skill-item">
                  <span>Node.js</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="80%"></div>
                  </div>
                </div>
                <div className="skill-item">
                  <span>Python</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="75%"></div>
                  </div>
                </div>
                <div className="skill-item">
                  <span>MongoDB</span>
                  <div className="skill-bar">
                    <div className="skill-progress" data-width="70%"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Projects Section */}
      <section id="projects" className="projects">
        <div className="container">
          <h2 className="section-title">Featured Projects</h2>
          <div className="projects-grid">
            <div className="project-card">
              <div className="project-image">
                <div className="project-overlay">
                  <button className="project-btn">View Project</button>
                </div>
              </div>
              <div className="project-content">
                <h3>E-Commerce Platform</h3>
                <p>Full-stack e-commerce solution with React and Node.js</p>
                <div className="project-tech">
                  <span>React</span>
                  <span>Node.js</span>
                  <span>MongoDB</span>
                </div>
              </div>
            </div>
            <div className="project-card">
              <div className="project-image">
                <div className="project-overlay">
                  <button className="project-btn">View Project</button>
                </div>
              </div>
              <div className="project-content">
                <h3>AI Dashboard</h3>
                <p>Real-time analytics dashboard with AI insights</p>
                <div className="project-tech">
                  <span>React</span>
                  <span>Python</span>
                  <span>TensorFlow</span>
                </div>
              </div>
            </div>
            <div className="project-card">
              <div className="project-image">
                <div className="project-overlay">
                  <button className="project-btn">View Project</button>
                </div>
              </div>
              <div className="project-content">
                <h3>Mobile App</h3>
                <p>Cross-platform mobile application with React Native</p>
                <div className="project-tech">
                  <span>React Native</span>
                  <span>Firebase</span>
                  <span>Redux</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section id="contact" className="contact">
        <div className="container">
          <h2 className="section-title">Get In Touch</h2>
          <div className="contact-content">
            <div className="contact-info">
              <h3>Let's work together</h3>
              <p>Ready to bring your ideas to life? Let's discuss your next project.</p>
              <div className="contact-methods">
                <div className="contact-method">
                  <span className="contact-icon">📧</span>
                  <span>fenontsoa@gmail.com</span>
                </div>
                <div className="contact-method">
                  <span className="contact-icon">📱</span>
                  <span>+261 34 25 140 01</span>
                </div>
                <div className="contact-method">
                  <span className="contact-icon">📍</span>
                  <span>Antananarivo, Madagascar</span>
                </div>
              </div>
            </div>
            <form className="contact-form">
              <div className="form-group">
                <input type="text" placeholder="Your Name" className="form-input" />
              </div>
              <div className="form-group">
                <input type="email" placeholder="Your Email" className="form-input" />
              </div>
              <div className="form-group">
                <textarea placeholder="Your Message" className="form-textarea" rows="5"></textarea>
              </div>
              <button type="submit" className="btn-primary">Send Message</button>
            </form>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="container">
          <div className="footer-content">
            <p>&copy; 2024 Fenontsoa D. ANDRIANARIVONDRIAKA. All rights reserved.</p>
            <div className="social-links">
              <a href="#" className="social-link">GitHub</a>
              <a href="#" className="social-link">LinkedIn</a>
              <a href="#" className="social-link">Twitter</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
