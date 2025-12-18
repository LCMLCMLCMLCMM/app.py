// 现代化UI和动画脚本

// 性能优化：防抖函数
function debounce(func, wait, immediate) {
    let timeout;
    return function() {
        const context = this, args = arguments;
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
}

// 性能优化：节流函数
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化所有功能
    initializeThemeToggle();
    initializeFlashMessages();
    initializeAnimations();
    initializeButtons();
    initializeForms();
    initializeHeroSection();
});

// 主题切换功能
function initializeThemeToggle() {
    const toggleButton = document.querySelector('.theme-toggle');
    if (toggleButton) {
        toggleButton.addEventListener('click', function(e) {
            e.preventDefault();
            
            // 添加点击动画
            this.classList.add('clicked');
            setTimeout(() => {
                this.classList.remove('clicked');
            }, 300);
            
            // 切换主题
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            
            // 保存主题偏好到本地存储
            localStorage.setItem('theme', newTheme);
            
            // 更新按钮文本
            this.textContent = newTheme === 'dark' ? '浅色模式' : '深色模式';
        });
    }
}

// 闪现消息功能
function initializeFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(function(message) {
        // 点击消息时隐藏
        message.addEventListener('click', function() {
            this.style.animation = 'fadeOut 0.3s ease forwards';
            setTimeout(() => {
                this.remove();
            }, 300);
        });
        
        // 3秒后自动隐藏
        setTimeout(() => {
            if (message.parentNode) {
                message.style.animation = 'fadeOut 0.5s ease forwards';
                setTimeout(() => {
                    message.remove();
                }, 500);
            }
        }, 3000);
    });
}

// 初始化动画效果 - 使用Intersection Observer优化性能
function initializeAnimations() {
    // 为卡片添加进入视口动画
    const cards = document.querySelectorAll('.card, .post');
    
    // 使用Intersection Observer API提升性能
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(throttle((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.animation = 'fadeIn 0.6s ease forwards';
                    entry.target.style.opacity = '1';
                    observer.unobserve(entry.target);
                }
            });
        }, 100), {
            threshold: 0.1
        });
        
        cards.forEach(card => {
            card.style.opacity = '0';
            observer.observe(card);
        });
    } else {
        // 降级处理：直接显示元素
        cards.forEach(card => {
            card.style.opacity = '1';
        });
    }
    
    // 为标题添加动画
    const titles = document.querySelectorAll('h1, h2, h3');
    titles.forEach((title, index) => {
        title.style.animationDelay = `${index * 0.1}s`;
    });
}

// 按钮效果
function initializeButtons() {
    const buttons = document.querySelectorAll('.btn');
    
    buttons.forEach(button => {
        // 添加涟漪效果
        button.addEventListener('click', function(e) {
            // 性能优化：限制涟漪效果的创建频率
            if (this.classList.contains('ripple-active')) return;
            
            this.classList.add('ripple-active');
            const x = e.clientX - e.target.getBoundingClientRect().left;
            const y = e.clientY - e.target.getBoundingClientRect().top;
            
            const ripple = document.createElement('span');
            ripple.classList.add('ripple');
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            
            this.appendChild(ripple);
            
            setTimeout(() => {
                ripple.remove();
                this.classList.remove('ripple-active');
            }, 600);
        });
        
        // 悬停效果
        button.addEventListener('mouseenter', function() {
            this.classList.add('hovered');
        });
        
        button.addEventListener('mouseleave', function() {
            this.classList.remove('hovered');
        });
    });
}

// 表单功能
function initializeForms() {
    const inputs = document.querySelectorAll('.form-control');
    
    inputs.forEach(input => {
        // 添加焦点效果
        input.addEventListener('focus', function() {
            this.parentElement.classList.add('focused');
        });
        
        input.addEventListener('blur', function() {
            this.parentElement.classList.remove('focused');
        });
        
        // 添加输入动画
        input.addEventListener('input', debounce(function() {
            if (this.value.length > 0) {
                this.classList.add('has-content');
            } else {
                this.classList.remove('has-content');
            }
        }, 300));
    });
}

// 初始化Hero部分动画
function initializeHeroSection() {
    const heroSection = document.querySelector('.hero-section');
    if (heroSection) {
        heroSection.style.opacity = '0';
        heroSection.style.transform = 'translateY(20px)';
        heroSection.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
        
        setTimeout(() => {
            heroSection.style.opacity = '1';
            heroSection.style.transform = 'translateY(0)';
        }, 100);
    }
}

// 平滑滚动
function smoothScrollTo(target) {
    const element = document.querySelector(target);
    if (element) {
        window.scrollTo({
            top: element.offsetTop - 80,
            behavior: 'smooth'
        });
    }
}

// 加载更多功能（用于文章列表）
function loadMorePosts() {
    const loadButton = document.querySelector('.load-more');
    if (loadButton) {
        loadButton.addEventListener('click', function() {
            const loading = this.querySelector('.loading');
            const text = this.querySelector('.text');
            
            // 显示加载状态
            if (loading) loading.style.display = 'inline-block';
            if (text) text.textContent = '加载中...';
            
            // 模拟加载过程
            setTimeout(() => {
                // 这里应该从服务器获取更多文章
                // 示例代码：
                // fetch('/api/posts?page=2')
                //   .then(response => response.json())
                //   .then(data => {
                //     renderPosts(data);
                //   });
                
                if (loading) loading.style.display = 'none';
                if (text) text.textContent = '加载更多';
                
                // 显示完成消息
                const message = document.createElement('div');
                message.className = 'flash-message success';
                message.textContent = '加载完成！';
                document.querySelector('.flash-messages').appendChild(message);
                
                initializeFlashMessages();
            }, 1500);
        });
    }
}

// 搜索功能
function initializeSearch() {
    const searchInput = document.querySelector('.search-input');
    const searchResults = document.querySelector('.search-results');
    
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function() {
            const query = this.value.trim();
            
            if (query.length > 0) {
                // 模拟搜索
                // 实际应用中应该调用搜索API
                if (searchResults) {
                    searchResults.style.display = 'block';
                    searchResults.innerHTML = `
                        <div class="search-result">
                            <div class="result-title">搜索结果示例</div>
                            <div class="result-excerpt">这是关于"${query}"的搜索结果示例</div>
                        </div>
                    `;
                }
            } else {
                if (searchResults) {
                    searchResults.style.display = 'none';
                }
            }
        }, 300));
    }
}

// 返回顶部按钮
function initializeBackToTop() {
    const backToTopButton = document.createElement('button');
    backToTopButton.innerHTML = '&uarr;';
    backToTopButton.className = 'back-to-top';
    backToTopButton.title = '返回顶部';
    document.body.appendChild(backToTopButton);
    
    window.addEventListener('scroll', throttle(function() {
        if (window.pageYOffset > 300) {
            backToTopButton.style.display = 'block';
        } else {
            backToTopButton.style.display = 'none';
        }
    }, 100));
    
    backToTopButton.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// 复制到剪贴板功能
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    
    // 显示成功消息
    const message = document.createElement('div');
    message.className = 'flash-message success';
    message.textContent = '已复制到剪贴板';
    document.querySelector('.flash-messages').appendChild(message);
    initializeFlashMessages();
}

// 导出功能
window.UI = {
    smoothScrollTo,
    copyToClipboard
};