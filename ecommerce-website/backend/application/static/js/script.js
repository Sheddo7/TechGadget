// Enhanced Cart Manager with Reviews & Ratings
class CartManager {
    constructor() {
        this.isLoggedIn = document.body.dataset.userAuthenticated === 'true';
        this.isProcessing = false;
        console.log('🛒 CartManager initialized. User logged in:', this.isLoggedIn);

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupCategoryFilters();
        this.setupSearchFunctionality();
        this.setupWishlistFunctionality();
        this.setupCartCounterEvents();
        this.setupStarRating();

        // Initialize cart from localStorage immediately
        this.initializeCartFromStorage();
        this.updateCartCounter();

        // Sync localStorage with server on page load
        this.syncLocalStorageToServer();

        console.log('🛒 CartManager setup complete');
    }

    initializeCartFromStorage() {
        // Ensure cart exists in localStorage
        if (!localStorage.getItem('cart')) {
            localStorage.setItem('cart', JSON.stringify([]));
        }
        console.log('💾 Cart initialized from localStorage');
    }

    async syncLocalStorageToServer() {
        if (!this.isLoggedIn) return;

        try {
            const localCart = JSON.parse(localStorage.getItem('cart')) || [];
            console.log('🔄 Syncing localStorage to server...', localCart);

            if (localCart.length === 0) return;

            // Clear existing server cart first
            await fetch('/api/cart/clear', { method: 'DELETE' });

            // Add all items from localStorage to server
            for (const item of localCart) {
                await this.syncToServer(item.product_id, item.quantity, 'add');
            }

            console.log('✅ LocalStorage synced to server');
        } catch (error) {
            console.error('❌ Failed to sync localStorage to server:', error);
        }
    }

    setupEventListeners() {
        document.addEventListener('click', (e) => {
            if (this.isProcessing) return;

            const addToCartBtn = e.target.closest('.add-to-cart-btn');
            if (addToCartBtn) {
                e.preventDefault();
                e.stopPropagation();
                this.handleAddToCart(addToCartBtn);
                return;
            }

            const removeBtn = e.target.closest('.remove-btn');
            if (removeBtn) {
                e.preventDefault();
                const productId = removeBtn.getAttribute('data-product-id');
                this.handleRemoveFromCart(productId);
                return;
            }

            const quantityBtn = e.target.closest('.quantity-btn');
            if (quantityBtn) {
                e.preventDefault();
                e.stopPropagation();
                this.handleQuantityChange(quantityBtn);
                return;
            }

            if (e.target.classList.contains('category-filter') || e.target.closest('.category-filter')) {
                this.handleCategoryFilter(e);
            }

            if (e.target.classList.contains('quick-filter')) {
                this.handleQuickFilter(e.target);
            }

            if (e.target.classList.contains('remove-filter')) {
                this.handleRemoveFilter(e.target);
            }

            if (e.target.classList.contains('clear-filters')) {
                this.handleClearFilters();
            }
        });
    }

    handleAddToCart(button) {
        if (this.isProcessing) return;

        const productId = button.getAttribute('data-product-id');
        const productName = button.getAttribute('data-product-name');
        const productPrice = parseFloat(button.getAttribute('data-product-price'));
        const productImage = button.getAttribute('data-product-image');

        let quantity = 1;
        const quantityInput = document.getElementById('quantity');
        if (quantityInput) {
            quantity = parseInt(quantityInput.value) || 1;
        }

        console.log('🛒 Adding to cart:', { productId, productName, productPrice, productImage, quantity });
        this.addToCart(productId, productName, productPrice, productImage, quantity);
    }

    async addToCart(productId, name, price, imageUrl, quantity = 1) {
        if (this.isProcessing) return;
        this.isProcessing = true;

        try {
            // Add to localStorage first for immediate feedback
            let localCart = JSON.parse(localStorage.getItem('cart')) || [];
            const existingItemIndex = localCart.findIndex(item => item.product_id == productId);

            if (existingItemIndex !== -1) {
                // Update existing item - Only add the specified quantity
                localCart[existingItemIndex].quantity += quantity;
                console.log(`🔄 Updated existing item: ${localCart[existingItemIndex].quantity} total`);
            } else {
                // Add new item
                localCart.push({
                    product_id: parseInt(productId),
                    name: name,
                    price: price,
                    image_url: imageUrl,
                    quantity: quantity
                });
                console.log('✅ Added new item to cart');
            }

            localStorage.setItem('cart', JSON.stringify(localCart));
            console.log('💾 Saved to localStorage:', localCart);

            // Update UI immediately
            this.updateCartCounter();
            this.showNotification(`✅ "${name}" added to cart!`);

            // Sync to database if user is logged in
            if (this.isLoggedIn) {
                await this.syncToServer(productId, localCart[existingItemIndex]?.quantity || quantity, 'add');
            }

        } catch (error) {
            console.error('❌ Error adding to cart:', error);
            this.showNotification('❌ Failed to add item to cart', 'error');
        } finally {
            this.isProcessing = false;
        }
    }

    async handleRemoveFromCart(productId) {
        if (this.isProcessing) return;
        this.isProcessing = true;

        console.log('🗑️ Removing from cart:', productId);

        try {
            // Visual feedback
            const cartItem = document.getElementById(`cart-item-${productId}`);
            const removeBtn = document.querySelector(`.remove-btn[data-product-id="${productId}"]`);

            if (cartItem) {
                cartItem.classList.add('removing');
            }
            if (removeBtn) {
                removeBtn.classList.add('removing');
                removeBtn.disabled = true;
            }

            // Remove from localStorage FIRST
            let localCart = JSON.parse(localStorage.getItem('cart')) || [];
            const initialLength = localCart.length;
            localCart = localCart.filter(item => item.product_id != productId);

            if (localCart.length === initialLength) {
                console.log('❌ Item not found in localStorage');
                return;
            }

            localStorage.setItem('cart', JSON.stringify(localCart));
            console.log('✅ Removed from localStorage. New cart:', localCart);

            // Update UI immediately
            this.updateCartCounter();

            // Sync to server if logged in
            if (this.isLoggedIn) {
                await this.syncToServer(productId, 0, 'remove');
            }

            // Show notification
            this.showNotification('✅ Item removed from cart');

            // Handle UI updates for cart page
            if (window.location.pathname.includes('/cart')) {
                if (localCart.length === 0) {
                    this.handleEmptyCartUI();
                } else {
                    // Update the specific item display
                    if (cartItem) {
                        cartItem.remove();
                    }
                    this.updateCartSummaryFromLocalStorage();
                }
            }

        } catch (error) {
            console.error('❌ Error removing from cart:', error);
            this.showNotification('❌ Failed to remove item', 'error');

            // Remove visual feedback on error
            const cartItem = document.getElementById(`cart-item-${productId}`);
            const removeBtn = document.querySelector(`.remove-btn[data-product-id="${productId}"]`);

            if (cartItem) cartItem.classList.remove('removing');
            if (removeBtn) {
                removeBtn.classList.remove('removing');
                removeBtn.disabled = false;
            }
        } finally {
            this.isProcessing = false;
        }
    }

    handleEmptyCartUI() {
        console.log('🛒 Cart is now empty, updating UI...');

        const cartItemsContainer = document.getElementById('cart-items');
        if (cartItemsContainer) {
            cartItemsContainer.innerHTML = `
                <div class="empty-cart-message">
                    <h3>Your cart is empty</h3>
                    <p>Add some products to get started!</p>
                    <a href="/products" class="cta-button">Browse Products</a>
                </div>
            `;
        }

        this.updateCartSummary(0, 0, 0);

        const checkoutBtn = document.getElementById('checkout-btn-active');
        if (checkoutBtn) {
            checkoutBtn.style.display = 'none';
        }
    }

    updateCartSummary(subtotal, shipping, total) {
        const subtotalElement = document.getElementById('summary-subtotal');
        const shippingElement = document.getElementById('summary-shipping');
        const totalElement = document.getElementById('summary-total');

        if (subtotalElement) subtotalElement.textContent = `$${subtotal.toFixed(2)}`;
        if (shippingElement) shippingElement.textContent = shipping === 0 ? 'FREE' : `$${shipping.toFixed(2)}`;
        if (totalElement) totalElement.textContent = `$${total.toFixed(2)}`;
    }

    async handleQuantityChange(button) {
        if (this.isProcessing) return;
        this.isProcessing = true;

        const action = button.getAttribute('data-action');
        const productId = button.getAttribute('data-product-id');

        console.log(`🔄 Handling quantity change: ${action} for product ${productId}`);

        try {
            // Get current quantity from localStorage to ensure accuracy
            let localCart = JSON.parse(localStorage.getItem('cart')) || [];
            const itemIndex = localCart.findIndex(item => item.product_id == productId);

            if (itemIndex === -1) {
                console.log('❌ Item not found in cart');
                return;
            }

            let currentQuantity = localCart[itemIndex].quantity;
            let newQuantity = currentQuantity;

            if (action === 'increase') {
                newQuantity = currentQuantity + 1;
                console.log(`➕ Increasing quantity from ${currentQuantity} to ${newQuantity}`);
            } else if (action === 'decrease') {
                newQuantity = Math.max(1, currentQuantity - 1);
                console.log(`➖ Decreasing quantity from ${currentQuantity} to ${newQuantity}`);
            }

            await this.updateCartQuantity(productId, newQuantity);
        } catch (error) {
            console.error('❌ Error in handleQuantityChange:', error);
            this.showNotification('❌ Failed to update quantity', 'error');
        } finally {
            this.isProcessing = false;
        }
    }

    async updateCartQuantity(productId, quantity) {
        try {
            // Update localStorage
            let localCart = JSON.parse(localStorage.getItem('cart')) || [];
            const itemIndex = localCart.findIndex(item => item.product_id == productId);

            if (itemIndex !== -1) {
                if (quantity <= 0) {
                    await this.handleRemoveFromCart(productId);
                    return;
                } else {
                    const oldQuantity = localCart[itemIndex].quantity;
                    localCart[itemIndex].quantity = quantity;
                    localStorage.setItem('cart', JSON.stringify(localCart));

                    console.log(`📊 Updated quantity from ${oldQuantity} to ${quantity} for product ${productId}`);

                    // Update UI
                    this.updateCartCounter();

                    // Sync to server if logged in
                    if (this.isLoggedIn) {
                        await this.syncToServer(productId, quantity, 'update');
                    }

                    // Update the display in the cart
                    this.updateCartItemDisplay(productId, quantity);
                    this.updateCartSummaryFromLocalStorage();
                }
            }
        } catch (error) {
            console.error('❌ Error updating quantity:', error);
            this.showNotification('❌ Failed to update quantity', 'error');
        }
    }

    updateCartItemDisplay(productId, quantity) {
        // Update quantity display
        const quantityElement = document.querySelector(`#cart-item-${productId} .quantity`);
        if (quantityElement) {
            quantityElement.textContent = `Quantity: ${quantity}`;
        }

        // Update item total
        const localCart = JSON.parse(localStorage.getItem('cart')) || [];
        const item = localCart.find(item => item.product_id == productId);
        if (item) {
            const itemTotalElement = document.querySelector(`#cart-item-${productId} .item-total`);
            if (itemTotalElement) {
                const itemTotal = item.price * item.quantity;
                itemTotalElement.textContent = `Total: $${itemTotal.toFixed(2)}`;
            }
        }
    }

    updateCartSummaryFromLocalStorage() {
        try {
            const localCart = JSON.parse(localStorage.getItem('cart')) || [];
            let subtotal = 0;

            localCart.forEach(item => {
                if (item && item.price && item.quantity) {
                    subtotal += item.price * item.quantity;
                }
            });

            const shipping = subtotal > 50 ? 0 : 5.99;
            const total = subtotal + shipping;

            this.updateCartSummary(subtotal, shipping, total);
        } catch (error) {
            console.error('❌ Error updating cart summary:', error);
        }
    }

    async syncToServer(productId, quantity, action) {
        try {
            let response;
            let success = false;

            if (action === 'add' || action === 'update') {
                response = await fetch('/api/cart', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        product_id: parseInt(productId),
                        quantity: quantity
                    })
                });
                success = response && response.ok;
            } else if (action === 'remove') {
                response = await fetch(`/api/cart/${productId}`, {
                    method: 'DELETE'
                });
                success = response && response.ok;
            }

            if (success) {
                console.log(`✅ Successfully synced ${action} to server`);
                return true;
            } else {
                throw new Error(`Server returned ${response?.status}`);
            }

        } catch (error) {
            console.error(`❌ Sync ${action} error:`, error);
            return false;
        }
    }

    updateCartCounter() {
        try {
            const localCart = JSON.parse(localStorage.getItem('cart')) || [];
            let totalItems = 0;

            localCart.forEach(item => {
                if (item && item.quantity) {
                    totalItems += parseInt(item.quantity);
                }
            });

            console.log('📊 Cart counter update:', totalItems, 'items in cart');
            this.displayCartCounter(totalItems);

        } catch (error) {
            console.error('❌ Error updating cart counter:', error);
            this.displayCartCounter(0);
        }
    }

    displayCartCounter(count) {
        let cartCounter = document.getElementById('cart-counter');
        const cartLink = document.querySelector('.cart-link');

        if (!cartCounter && cartLink) {
            cartCounter = document.createElement('span');
            cartCounter.id = 'cart-counter';
            cartCounter.className = 'cart-counter';
            cartLink.appendChild(cartCounter);
        }

        if (cartCounter) {
            // Update count
            cartCounter.textContent = count > 99 ? '99+' : count;
            cartCounter.style.display = count > 0 ? 'flex' : 'none';

            // Remove all state classes
            cartCounter.classList.remove('low', 'medium', 'high', 'very-high', 'updating');

            // Add appropriate state class based on count
            if (count === 0) {
                cartCounter.style.display = 'none';
            } else if (count <= 3) {
                cartCounter.classList.add('low');
            } else if (count <= 9) {
                cartCounter.classList.add('medium');
            } else if (count <= 20) {
                cartCounter.classList.add('high');
            } else {
                cartCounter.classList.add('very-high');
            }

            // Add update animation
            cartCounter.classList.add('updating');
            setTimeout(() => {
                cartCounter.classList.remove('updating');
            }, 200);
        }
    }
    showNotification(message, type = 'success') {
        const existingNotifications = document.querySelectorAll('.custom-notification');
        existingNotifications.forEach(notification => notification.remove());

        const notification = document.createElement('div');
        notification.className = `custom-notification flash-message ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#27ae60' : '#e74c3c'};
            color: white;
            padding: 1rem 2rem;
            border-radius: 5px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            font-weight: bold;
        `;

        document.body.appendChild(notification);

        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 3000);
    }

    setupCategoryFilters() {
        // Category filter functionality
        const categoryFilters = document.querySelectorAll('.category-filter');
        categoryFilters.forEach(filter => {
            filter.addEventListener('click', (e) => {
                e.preventDefault();
                const categoryId = filter.getAttribute('data-category-id');
                window.location.href = `/products?category=${categoryId}`;
            });
        });
    }

    setupSearchFunctionality() {
        // Search functionality
        const searchForm = document.querySelector('.search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                const searchInput = searchForm.querySelector('input[type="search"]');
                if (searchInput && searchInput.value.trim()) {
                    e.preventDefault();
                    const query = searchInput.value.trim();
                    window.location.href = `/products?search=${encodeURIComponent(query)}`;
                }
            });
        }
    }

    setupWishlistFunctionality() {
        // Wishlist functionality
        const wishlistButtons = document.querySelectorAll('.wishlist-btn');
        wishlistButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const productId = button.getAttribute('data-product-id');
                this.toggleWishlist(productId, button);
            });
        });
    }

    setupCartCounterEvents() {
        // Additional cart counter events if needed
    }

    setupStarRating() {
        // Star rating functionality
        const ratingStars = document.querySelectorAll('.rating-stars');
        ratingStars.forEach(stars => {
            const rating = parseFloat(stars.getAttribute('data-rating'));
            this.updateStarRating(stars, rating);
        });
    }

    toggleWishlist(productId, button) {
        // Wishlist toggle functionality
        console.log('Toggle wishlist for product:', productId);
        // Implement wishlist functionality here
    }

    updateStarRating(starsElement, rating) {
        // Update star rating display
        if (starsElement) {
            starsElement.style.setProperty('--rating', rating);
        }
    }

    handleCategoryFilter(e) {
        const filter = e.target.closest('.category-filter');
        if (filter) {
            const categoryId = filter.getAttribute('data-category-id');
            window.location.href = `/products?category=${categoryId}`;
        }
    }

    handleQuickFilter(filter) {
        const filterType = filter.getAttribute('data-filter');
        const filterValue = filter.getAttribute('data-value');
        // Implement quick filter functionality
        console.log('Quick filter:', filterType, filterValue);
    }

    handleRemoveFilter(button) {
        const filterType = button.getAttribute('data-filter');
        // Implement remove filter functionality
        console.log('Remove filter:', filterType);
    }

    handleClearFilters() {
        // Implement clear all filters functionality
        window.location.href = '/products';
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 DOM loaded, initializing application...');

    // Initialize cart manager
    window.cartManager = new CartManager();

    // If we're on the cart page, display localStorage cart instead of server cart
    if (window.location.pathname.includes('/cart')) {
        displayLocalStorageCart();
    }

    // Make addToCart globally available
    window.addToCart = function(productId, name, price, imageUrl, quantity = 1) {
        if (window.cartManager) {
            window.cartManager.addToCart(productId, name, price, imageUrl, quantity);
        }
    };

    // Setup review form validation
    setupReviewFormValidation();

    // Ensure cart counter exists and is accurate
    ensureCartCounter();

    console.log('✅ Application initialized successfully');
});

// Display localStorage cart on cart page
function displayLocalStorageCart() {
    try {
        const localCart = JSON.parse(localStorage.getItem('cart')) || [];
        const cartItemsContainer = document.getElementById('cart-items');

        if (!cartItemsContainer) return;

        if (localCart.length === 0) {
            cartItemsContainer.innerHTML = `
                <div class="empty-cart-message">
                    <h3>Your cart is empty</h3>
                    <p>Add some products to get started!</p>
                    <a href="/products" class="cta-button">Browse Products</a>
                </div>
            `;
            return;
        }

        // Clear existing items
        cartItemsContainer.innerHTML = '';

        // Add items from localStorage
        localCart.forEach(item => {
            const itemTotal = item.price * item.quantity;
            const cartItem = document.createElement('div');
            cartItem.className = 'cart-item';
            cartItem.id = `cart-item-${item.product_id}`;
            cartItem.innerHTML = `
                <div class="cart-item-image">
                    <img src="${item.image_url}" alt="${item.name}" onerror="this.src='https://via.placeholder.com/100x100?text=No+Image'">
                </div>
                <div class="cart-item-details">
                    <h3>${item.name}</h3>
                    <p class="item-price">Price: $${item.price.toFixed(2)}</p>
                    <div class="quantity-controls">
                        <button class="quantity-btn" data-action="decrease" data-product-id="${item.product_id}">-</button>
                        <span class="quantity">Quantity: ${item.quantity}</span>
                        <button class="quantity-btn" data-action="increase" data-product-id="${item.product_id}">+</button>
                    </div>
                    <p class="item-total">Total: $${itemTotal.toFixed(2)}</p>
                    <button class="remove-btn" data-product-id="${item.product_id}">
                        <span class="remove-text">Remove</span>
                        <span class="removing-text" style="display: none;">Removing...</span>
                    </button>
                </div>
            `;
            cartItemsContainer.appendChild(cartItem);
        });

        // Update summary
        if (window.cartManager) {
            window.cartManager.updateCartSummaryFromLocalStorage();
        }

    } catch (error) {
        console.error('❌ Error displaying localStorage cart:', error);
    }
}

// Review form validation
function setupReviewFormValidation() {
    const reviewForm = document.getElementById('review-form');
    if (reviewForm) {
        reviewForm.addEventListener('submit', function(e) {
            const rating = document.querySelector('input[name="rating"]:checked');
            const title = document.getElementById('review-title').value.trim();
            const comment = document.getElementById('review-comment').value.trim();

            if (!rating) {
                e.preventDefault();
                alert('Please select a rating');
                return false;
            }

            if (!title) {
                e.preventDefault();
                alert('Please enter a review title');
                return false;
            }

            if (!comment) {
                e.preventDefault();
                alert('Please enter your review comment');
                return false;
            }
        });
    }
}

// Global functions for backward compatibility
window.removeFromCart = function(productId) {
    if (window.cartManager) {
        window.cartManager.handleRemoveFromCart(productId);
    }
};

window.updateQuantity = function(productId, quantity) {
    if (window.cartManager) {
        window.cartManager.updateCartQuantity(productId, quantity);
    }
};

// Force cart counter to show on all pages and be accurate
function ensureCartCounter() {
    const cartLink = document.querySelector('a[href="/cart"]');
    if (cartLink && !document.getElementById('cart-counter')) {
        const cartCounter = document.createElement('span');
        cartCounter.id = 'cart-counter';
        cartCounter.className = 'cart-counter';
        cartCounter.style.display = 'flex';
        cartLink.appendChild(cartCounter);

        try {
            const localCart = JSON.parse(localStorage.getItem('cart')) || [];
            let totalItems = 0;
            localCart.forEach(item => {
                if (item && item.quantity) {
                    totalItems += parseInt(item.quantity);
                }
            });
            cartCounter.textContent = totalItems > 99 ? '99+' : totalItems;

            if (totalItems === 0) {
                cartCounter.style.background = '#95a5a6';
            } else {
                cartCounter.style.background = '#e74c3c';
            }
        } catch (error) {
            cartCounter.textContent = '0';
            cartCounter.style.background = '#95a5a6';
        }
    }
}

// Debug functions
window.clearCart = function() {
    localStorage.setItem('cart', JSON.stringify([]));
    if (window.cartManager) {
        window.cartManager.updateCartCounter();
        if (window.location.pathname.includes('/cart')) {
            displayLocalStorageCart();
        }
    }
    console.log('🔄 Cart cleared from localStorage');
};

window.showCart = function() {
    const cart = JSON.parse(localStorage.getItem('cart')) || [];
    console.log('📋 Current cart contents:', cart);
    alert('Cart contents logged to console. Total items: ' + cart.reduce((sum, item) => sum + (item.quantity || 0), 0));
    return cart;
};

window.syncCart = function() {
    if (window.cartManager) {
        window.cartManager.syncLocalStorageToServer();
    }
};

// Run this on every page to ensure cart counter exists
document.addEventListener('DOMContentLoaded', ensureCartCounter);