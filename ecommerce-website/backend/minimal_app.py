from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

# Get the absolute path to the templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'application', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'application', 'static')

app = Flask(__name__,
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)
app.secret_key = 'your-super-secret-key-123-change-in-production'
app.config['DATABASE'] = 'ecommerce.db'

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


# Updated User class to include is_admin
class User(UserMixin):
    def __init__(self, id, username, email, password_hash, created_at, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at
        self.is_admin = bool(is_admin)

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if not user:
            return None
        return User(id=user['id'], username=user['username'], email=user['email'],
                    password_hash=user['password_hash'], created_at=user['created_at'],
                    is_admin=user['is_admin'])

    @staticmethod
    def find_by_username(username):
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if not user:
            return None
        return User(id=user['id'], username=user['username'], email=user['email'],
                    password_hash=user['password_hash'], created_at=user['created_at'],
                    is_admin=user['is_admin'])


class Order:
    def __init__(self, id, user_id, order_number, total_amount, status,
                 shipping_address, billing_address, payment_method,
                 payment_status, created_at, updated_at):
        self.id = id
        self.user_id = user_id
        self.order_number = order_number
        self.total_amount = total_amount
        self.status = status
        self.shipping_address = shipping_address
        self.billing_address = billing_address
        self.payment_method = payment_method
        self.payment_status = payment_status
        self.created_at = created_at
        self.updated_at = updated_at

    @staticmethod
    def create_order(user_id, cart_items, shipping_address, billing_address, payment_method):
        conn = get_db_connection()

        try:
            # Calculate total amount
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)

            # Generate unique order number
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{user_id}-{int(datetime.now().timestamp()) % 10000}"

            # Create order
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO orders (user_id, order_number, total_amount, shipping_address, billing_address,
                                               payment_method)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ''',
                           (user_id, order_number, total_amount, shipping_address, billing_address, payment_method))

            order_id = cursor.lastrowid

            # Create order items
            for item in cart_items:
                cursor.execute('''
                               INSERT INTO order_items (order_id, product_id, product_name, product_price, quantity,
                                                        total_price)
                               VALUES (?, ?, ?, ?, ?, ?)
                               ''', (order_id, item['product_id'], item['name'], item['price'], item['quantity'],
                                     item['price'] * item['quantity']))

            # Clear user's cart
            cursor.execute('DELETE FROM cart_items WHERE user_id = ?', (user_id,))

            conn.commit()
            return order_id, order_number

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_user_orders(user_id):
        conn = get_db_connection()
        orders = conn.execute('''
                              SELECT *
                              FROM orders
                              WHERE user_id = ?
                              ORDER BY created_at DESC
                              ''', (user_id,)).fetchall()
        conn.close()
        return orders

    @staticmethod
    def get_order_details(order_id):
        conn = get_db_connection()
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        order_items = conn.execute('''
                                   SELECT oi.*, p.image_url
                                   FROM order_items oi
                                            LEFT JOIN products p ON oi.product_id = p.id
                                   WHERE oi.order_id = ?
                                   ''', (order_id,)).fetchall()
        conn.close()
        return order, order_items


class Address:
    def __init__(self, id, user_id, address_type, full_name, street_address,
                 city, state, postal_code, country, phone_number, is_default, created_at):
        self.id = id
        self.user_id = user_id
        self.address_type = address_type
        self.full_name = full_name
        self.street_address = street_address
        self.city = city
        self.state = state
        self.postal_code = postal_code
        self.country = country
        self.phone_number = phone_number
        self.is_default = is_default
        self.created_at = created_at

    @staticmethod
    def get_user_addresses(user_id, address_type=None):
        conn = get_db_connection()
        if address_type:
            addresses = conn.execute(
                'SELECT * FROM addresses WHERE user_id = ? AND address_type = ? ORDER BY is_default DESC, created_at DESC',
                (user_id, address_type)
            ).fetchall()
        else:
            addresses = conn.execute(
                'SELECT * FROM addresses WHERE user_id = ? ORDER BY address_type, is_default DESC, created_at DESC',
                (user_id,)
            ).fetchall()
        conn.close()
        return addresses

    @staticmethod
    def create_address(user_id, address_type, full_name, street_address, city, state, postal_code, country,
                       phone_number, is_default=False):
        conn = get_db_connection()

        # If setting as default, remove default from other addresses of same type
        if is_default:
            conn.execute(
                'UPDATE addresses SET is_default = 0 WHERE user_id = ? AND address_type = ?',
                (user_id, address_type)
            )

        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO addresses (user_id, address_type, full_name, street_address, city, state,
                                              postal_code, country, phone_number, is_default)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (user_id, address_type, full_name, street_address, city, state, postal_code, country,
                             phone_number, is_default))

        address_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return address_id


class Wishlist:
    def __init__(self, id, user_id, name, is_public, created_at):
        self.id = id
        self.user_id = user_id
        self.name = name
        self.is_public = bool(is_public)
        self.created_at = created_at

    @staticmethod
    def get_user_wishlist(user_id):
        """Get or create user's default wishlist"""
        conn = get_db_connection()
        try:
            wishlist = conn.execute(
                'SELECT * FROM wishlists WHERE user_id = ? ORDER BY created_at LIMIT 1',
                (user_id,)
            ).fetchone()

            if not wishlist:
                # Create default wishlist
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO wishlists (user_id, name) VALUES (?, ?)',
                    (user_id, 'My Wishlist')
                )
                wishlist_id = cursor.lastrowid
                conn.commit()
                wishlist = conn.execute(
                    'SELECT * FROM wishlists WHERE id = ?', (wishlist_id,)
                ).fetchone()

            return wishlist
        finally:
            conn.close()

    @staticmethod
    def get_wishlist_items(wishlist_id):
        conn = get_db_connection()
        items = conn.execute('''
                             SELECT wi.*, p.name, p.price, p.image_url, p.stock
                             FROM wishlist_items wi
                                      JOIN products p ON wi.product_id = p.id
                             WHERE wi.wishlist_id = ?
                             ORDER BY wi.created_at DESC
                             ''', (wishlist_id,)).fetchall()
        conn.close()
        return items

    @staticmethod
    def add_to_wishlist(wishlist_id, product_id):
        conn = get_db_connection()
        try:
            conn.execute(
                'INSERT OR IGNORE INTO wishlist_items (wishlist_id, product_id) VALUES (?, ?)',
                (wishlist_id, product_id)
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    @staticmethod
    def remove_from_wishlist(wishlist_id, product_id):
        conn = get_db_connection()
        conn.execute(
            'DELETE FROM wishlist_items WHERE wishlist_id = ? AND product_id = ?',
            (wishlist_id, product_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def is_in_wishlist(wishlist_id, product_id):
        conn = get_db_connection()
        item = conn.execute(
            'SELECT 1 FROM wishlist_items WHERE wishlist_id = ? AND product_id = ?',
            (wishlist_id, product_id)
        ).fetchone()
        conn.close()
        return item is not None

    @staticmethod
    def get_public_wishlists():
        conn = get_db_connection()
        wishlists = conn.execute('''
                                 SELECT w.*, u.username, COUNT(wi.id) as item_count
                                 FROM wishlists w
                                          JOIN users u ON w.user_id = u.id
                                          LEFT JOIN wishlist_items wi ON w.id = wi.wishlist_id
                                 WHERE w.is_public = 1
                                 GROUP BY w.id
                                 ORDER BY w.created_at DESC
                                 ''').fetchall()
        conn.close()
        return wishlists

    @staticmethod
    def get_wishlist_by_id(wishlist_id):
        conn = get_db_connection()
        wishlist = conn.execute('''
                                SELECT w.*, u.username
                                FROM wishlists w
                                         JOIN users u ON w.user_id = u.id
                                WHERE w.id = ?
                                ''', (wishlist_id,)).fetchone()
        conn.close()
        return wishlist


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


def init_database():
    conn = get_db_connection()

    try:
        # Create categories table
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS categories
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         name TEXT NOT NULL,
                         slug TEXT UNIQUE NOT NULL,
                         description TEXT,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                     )
                     ''')

        # Create products table with category_id
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS products
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         name TEXT NOT NULL,
                         price REAL NOT NULL,
                         description TEXT,
                         image_url TEXT,
                         category_id INTEGER,
                         stock INTEGER DEFAULT 0,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY (category_id) REFERENCES categories (id)
                     )
                     ''')

        # Create users table with is_admin column - FIXED: Check if column exists
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS users
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         username TEXT UNIQUE NOT NULL,
                         email TEXT UNIQUE NOT NULL,
                         password_hash TEXT NOT NULL,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                     )
                     ''')

        # Check if is_admin column exists in users table, if not add it
        try:
            conn.execute('SELECT is_admin FROM users LIMIT 1')
        except sqlite3.OperationalError:
            print("🔄 Adding is_admin column to users table...")
            conn.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')

        # Create cart_items table
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS cart_items
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         product_id INTEGER NOT NULL,
                         quantity INTEGER NOT NULL DEFAULT 1,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         FOREIGN KEY (product_id) REFERENCES products (id),
                         UNIQUE (user_id,product_id)
                     )
                     ''')

        # Enhanced orders table with more fields
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS orders
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         order_number TEXT UNIQUE NOT NULL,
                         total_amount REAL NOT NULL,
                         status TEXT DEFAULT 'pending',
                         shipping_address TEXT,
                         billing_address TEXT,
                         payment_method TEXT,
                         payment_status TEXT DEFAULT 'pending',
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY (user_id) REFERENCES users (id)
                     )
                     ''')

        # Enhanced order_items table
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS order_items
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         order_id INTEGER NOT NULL,
                         product_id INTEGER NOT NULL,
                         product_name TEXT NOT NULL,
                         product_price REAL NOT NULL,
                         quantity INTEGER NOT NULL,
                         total_price REAL NOT NULL,
                         FOREIGN KEY (order_id) REFERENCES orders (id),
                         FOREIGN KEY (product_id) REFERENCES products (id)
                     )
                     ''')

        # Create addresses table for user addresses
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS addresses
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         user_id INTEGER NOT NULL,
                         address_type TEXT NOT NULL,
                         full_name TEXT NOT NULL,
                         street_address TEXT NOT NULL,
                         city TEXT NOT NULL,
                         state TEXT NOT NULL,
                         postal_code TEXT NOT NULL,
                         country TEXT DEFAULT 'US',
                         phone_number TEXT,
                         is_default BOOLEAN DEFAULT 0,
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY (user_id) REFERENCES users (id)
                     )
                     ''')

        # Create reviews table for product reviews
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS reviews
                     (
                         id INTEGER PRIMARY KEY AUTOINCREMENT,
                         product_id INTEGER NOT NULL,
                         user_id INTEGER NOT NULL,
                         rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                         title TEXT NOT NULL,
                         comment TEXT NOT NULL,
                         status TEXT DEFAULT 'pending',
                         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                         FOREIGN KEY (product_id) REFERENCES products (id),
                         FOREIGN KEY (user_id) REFERENCES users (id),
                         UNIQUE (user_id, product_id)
                     )
                     ''')

        # Create wishlists table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wishlists
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT DEFAULT 'My Wishlist',
                is_public BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Create wishlist_items table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wishlist_items
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wishlist_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (wishlist_id) REFERENCES wishlists (id),
                FOREIGN KEY (product_id) REFERENCES products (id),
                UNIQUE (wishlist_id, product_id)
            )
        ''')

        print("✅ All tables created successfully")

        # Check if categories exist
        category_count = conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0]

        if category_count == 0:
            # Insert sample categories
            sample_categories = [
                ('Smartphones', 'smartphones', 'Latest smartphones and mobile devices'),
                ('Laptops', 'laptops', 'Laptops, notebooks and computing devices'),
                ('Audio', 'audio', 'Headphones, speakers and audio equipment'),
                ('Wearables', 'wearables', 'Smartwatches and wearable technology'),
                ('Accessories', 'accessories', 'Cases, chargers and tech accessories')
            ]

            conn.executemany('''
                             INSERT INTO categories (name, slug, description)
                             VALUES (?, ?, ?)
                             ''', sample_categories)
            print("✅ Sample categories inserted")

        # Check if products exist
        product_count = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]

        if product_count == 0:
            # Insert sample products with category relationships
            sample_products = [
                ('Wireless Bluetooth Headphones', 99.99, 'High-quality wireless headphones with noise cancellation',
                 'https://via.placeholder.com/300x200/3498db/ffffff?text=Headphones', 15, 3),
                ('Smartphone X Pro', 899.99, 'Latest smartphone with advanced camera and processor',
                 'https://via.placeholder.com/300x200/e74c3c/ffffff?text=Smartphone+X', 10, 1),
                ('Gaming Laptop Pro', 1299.99, 'High-performance laptop for gaming and work',
                 'https://via.placeholder.com/300x200/2ecc71/ffffff?text=Gaming+Laptop', 8, 2),
                ('Smart Watch Series 5', 249.99, 'Feature-rich smartwatch with health monitoring',
                 'https://via.placeholder.com/300x200/9b59b6/ffffff?text=Smart+Watch', 20, 4),
                ('Wireless Earbuds', 79.99, 'True wireless earbuds with charging case',
                 'https://via.placeholder.com/300x200/3498db/ffffff?text=Earbuds', 25, 3),
                ('Ultra-Thin Laptop', 899.99, 'Lightweight and powerful ultrabook',
                 'https://via.placeholder.com/300x200/2ecc71/ffffff?text=Ultrabook', 12, 2),
                ('Phone Case - Premium', 29.99, 'Protective case with premium materials',
                 'https://via.placeholder.com/300x200/95a5a6/ffffff?text=Phone+Case', 50, 5),
                ('Wireless Charger', 39.99, 'Fast wireless charging pad',
                 'https://via.placeholder.com/300x200/95a5a6/ffffff?text=Charger', 30, 5)
            ]

            conn.executemany('''
                             INSERT INTO products (name, price, description, image_url, stock, category_id)
                             VALUES (?, ?, ?, ?, ?, ?)
                             ''', sample_products)
            print("✅ Sample products inserted")

        # Update existing products that have NULL category_id to a default category
        try:
            conn.execute('UPDATE products SET category_id = 1 WHERE category_id IS NULL')
        except sqlite3.OperationalError:
            print("⚠️  Could not update products category_id - column might not exist yet")

        # Check if we have any products with NULL category_id after update
        try:
            null_category_count = conn.execute('SELECT COUNT(*) FROM products WHERE category_id IS NULL').fetchone()[0]
            if null_category_count > 0:
                print(f"⚠️  {null_category_count} products still have NULL category_id")
        except sqlite3.OperationalError:
            print("⚠️  category_id column doesn't exist in products table")

        # Create admin user and demo user
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if user_count == 0:
            # Create admin user
            admin_password_hash = generate_password_hash('admin123')
            try:
                conn.execute('''
                             INSERT INTO users (username, email, password_hash, is_admin)
                             VALUES (?, ?, ?, ?)
                             ''', ('admin', 'admin@example.com', admin_password_hash, 1))
                print("✅ Admin user created - username: 'admin', password: 'admin123'")

                # Create demo user
                demo_password_hash = generate_password_hash('demo123')
                conn.execute('''
                             INSERT INTO users (username, email, password_hash, is_admin)
                             VALUES (?, ?, ?, ?)
                             ''', ('demo', 'demo@example.com', demo_password_hash, 0))
                print("✅ Demo user created - username: 'demo', password: 'demo123'")

                # Create additional users for sample reviews
                additional_users = [
                    ('john_doe', 'john@example.com', generate_password_hash('password123'), 0),
                    ('jane_smith', 'jane@example.com', generate_password_hash('password123'), 0),
                    ('mike_wilson', 'mike@example.com', generate_password_hash('password123'), 0),
                    ('sarah_jones', 'sarah@example.com', generate_password_hash('password123'), 0)
                ]

                conn.executemany('''
                                 INSERT INTO users (username, email, password_hash, is_admin)
                                 VALUES (?, ?, ?, ?)
                                 ''', additional_users)
                print("✅ Additional users created for sample reviews")
            except sqlite3.OperationalError as e:
                # If is_admin column doesn't exist yet, create users without it
                print("⚠️  Creating users without is_admin column...")
                conn.execute('''
                             INSERT INTO users (username, email, password_hash)
                             VALUES (?, ?, ?)
                             ''', ('admin', 'admin@example.com', admin_password_hash))
                conn.execute('''
                             INSERT INTO users (username, email, password_hash)
                             VALUES (?, ?, ?)
                             ''', ('demo', 'demo@example.com', demo_password_hash))
        else:
            # Check if admin user exists, if not create one
            admin_user = conn.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
            if not admin_user:
                admin_password_hash = generate_password_hash('admin123')
                try:
                    conn.execute('''
                                 INSERT INTO users (username, email, password_hash, is_admin)
                                 VALUES (?, ?, ?, ?)
                                 ''', ('admin', 'admin@example.com', admin_password_hash, 1))
                    print("✅ Admin user created - username: 'admin', password: 'admin123'")
                except sqlite3.OperationalError:
                    conn.execute('''
                                 INSERT INTO users (username, email, password_hash)
                                 VALUES (?, ?, ?)
                                 ''', ('admin', 'admin@example.com', admin_password_hash))
                    print("✅ Admin user created (without admin privileges)")

        # Add sample reviews (each user reviews different products)
        try:
            review_count = conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
            if review_count == 0:
                # Get user IDs
                users = conn.execute('SELECT id, username FROM users').fetchall()
                user_dict = {user['username']: user['id'] for user in users}

                # Get product IDs
                products = conn.execute('SELECT id FROM products ORDER BY id').fetchall()
                product_ids = [product['id'] for product in products]

                sample_reviews = [
                    # User 1 (demo) reviews
                    (product_ids[0], user_dict['demo'], 5, 'Excellent headphones!',
                     'The sound quality is amazing and the noise cancellation works perfectly.', 'approved'),
                    (product_ids[2], user_dict['demo'], 4, 'Great gaming laptop',
                     'Handles all my games smoothly, but gets a bit warm during long sessions.', 'approved'),

                    # User 2 (john_doe) reviews
                    (product_ids[1], user_dict['john_doe'], 5, 'Love this phone!',
                     'The camera is incredible and the performance is smooth.', 'approved'),
                    (product_ids[4], user_dict['john_doe'], 4, 'Good earbuds',
                     'Comfortable and good sound quality, battery life could be better.', 'approved'),

                    # User 3 (jane_smith) reviews
                    (product_ids[3], user_dict['jane_smith'], 5, 'Best smartwatch',
                     'Health tracking features are very accurate and useful.', 'approved'),
                    (product_ids[6], user_dict['jane_smith'], 4, 'Nice phone case', 'Good protection and feels premium.',
                     'approved'),

                    # User 4 (mike_wilson) reviews
                    (product_ids[5], user_dict['mike_wilson'], 4, 'Solid ultrabook',
                     'Lightweight and powerful, perfect for travel.', 'approved'),
                    (product_ids[7], user_dict['mike_wilson'], 3, 'Decent charger',
                     'Works well but charging speed could be faster.', 'approved'),

                    # User 5 (sarah_jones) reviews
                    (product_ids[0], user_dict['sarah_jones'], 4, 'Great sound quality',
                     'Very comfortable and great battery life.', 'approved'),
                    (product_ids[1], user_dict['sarah_jones'], 5, 'Amazing camera', 'The portrait mode is incredible!',
                     'approved')
                ]

                try:
                    conn.executemany('''
                                     INSERT INTO reviews (product_id, user_id, rating, title, comment, status)
                                     VALUES (?, ?, ?, ?, ?, ?)
                                     ''', sample_reviews)
                    print("✅ Sample reviews inserted")
                except sqlite3.IntegrityError as e:
                    print(f"⚠️  Some reviews couldn't be inserted due to unique constraint: {e}")
                    # Insert reviews one by one to avoid the constraint error
                    for review in sample_reviews:
                        try:
                            conn.execute('''
                                         INSERT INTO reviews (product_id, user_id, rating, title, comment, status)
                                         VALUES (?, ?, ?, ?, ?, ?)
                                         ''', review)
                        except sqlite3.IntegrityError:
                            print(f"⚠️  Skipping duplicate review for user {review[1]} on product {review[0]}")
                    conn.commit()
        except sqlite3.OperationalError:
            print("⚠️  Reviews table not available yet")

        conn.commit()
        print("✅ Database initialization completed successfully!")

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()


def row_to_dict(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dict_list(rows):
    """Convert list of sqlite3.Row objects to list of dictionaries"""
    return [row_to_dict(row) for row in rows]


# Context processor for cart count
@app.context_processor
def inject_cart_count():
    cart_count = 0
    if current_user.is_authenticated:
        conn = get_db_connection()
        cart_result = conn.execute('''
                                   SELECT SUM(quantity) as total_quantity
                                   FROM cart_items
                                   WHERE user_id = ?
                                   ''', (current_user.id,)).fetchone()
        conn.close()

        if cart_result and cart_result['total_quantity']:
            cart_count = cart_result['total_quantity']

    return dict(cart_count=cart_count)


# =============================================
# ADMIN ROUTES
# =============================================

@app.route('/admin')
@login_required
def admin_dashboard():
    # Check if user is admin
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()

    # Get basic stats
    total_products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    total_orders = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_revenue = \
        conn.execute('SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status = "completed"').fetchone()[0]

    # Recent orders
    recent_orders = conn.execute('''
                                 SELECT o.*, u.username
                                 FROM orders o
                                          JOIN users u ON o.user_id = u.id
                                 ORDER BY o.created_at DESC LIMIT 5
                                 ''').fetchall()

    # Low stock products
    low_stock_products = conn.execute('''
                                      SELECT *
                                      FROM products
                                      WHERE stock < 10
                                      ORDER BY stock ASC LIMIT 5
                                      ''').fetchall()

    # Sales data for chart (last 30 days)
    sales_data = conn.execute('''
                              SELECT DATE (created_at) as date, COUNT (*) as order_count, SUM (total_amount) as revenue
                              FROM orders
                              WHERE created_at >= date ('now', '-30 days')
                              GROUP BY DATE (created_at)
                              ORDER BY date
                              ''').fetchall()

    conn.close()

    return render_template('admin/dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           total_users=total_users,
                           total_revenue=total_revenue,
                           recent_orders=recent_orders,
                           low_stock_products=low_stock_products,
                           sales_data=sales_data)


@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    products = conn.execute('''
                            SELECT p.*, c.name as category_name
                            FROM products p
                                     LEFT JOIN categories c ON p.category_id = c.id
                            ORDER BY p.created_at DESC
                            ''').fetchall()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()

    return render_template('admin/products.html', products=products, categories=categories)


@app.route('/admin/products/new', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()

    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        image_url = request.form.get('image_url')
        category_id = request.form.get('category_id')
        stock = request.form.get('stock', 0)

        try:
            conn.execute('''
                         INSERT INTO products (name, price, description, image_url, category_id, stock)
                         VALUES (?, ?, ?, ?, ?, ?)
                         ''', (name, price, description, image_url, category_id, stock))
            conn.commit()
            flash('✅ Product added successfully!', 'success')
            return redirect('/admin/products')
        except Exception as e:
            conn.rollback()
            flash(f'❌ Error adding product: {str(e)}', 'error')
        finally:
            conn.close()

    return render_template('admin/product_form.html', categories=categories, product=None)


@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    categories = conn.execute('SELECT * FROM categories').fetchall()

    if not product:
        flash('❌ Product not found', 'error')
        conn.close()
        return redirect('/admin/products')

    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        image_url = request.form.get('image_url')
        category_id = request.form.get('category_id')
        stock = request.form.get('stock', 0)

        try:
            conn.execute('''
                         UPDATE products
                         SET name        = ?,
                             price       = ?,
                             description = ?,
                             image_url   = ?,
                             category_id = ?,
                             stock       = ?
                         WHERE id = ?
                         ''', (name, price, description, image_url, category_id, stock, product_id))
            conn.commit()
            flash('✅ Product updated successfully!', 'success')
            return redirect('/admin/products')
        except Exception as e:
            conn.rollback()
            flash(f'❌ Error updating product: {str(e)}', 'error')
        finally:
            conn.close()

    return render_template('admin/product_form.html', product=product, categories=categories)


@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    try:
        # Check if product exists in any orders
        order_items = conn.execute('SELECT COUNT(*) FROM order_items WHERE product_id = ?', (product_id,)).fetchone()[0]

        if order_items > 0:
            flash('❌ Cannot delete product that exists in orders. Consider archiving instead.', 'error')
        else:
            conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
            conn.commit()
            flash('✅ Product deleted successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'❌ Error deleting product: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect('/admin/products')


@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    status_filter = request.args.get('status', 'all')

    conn = get_db_connection()

    if status_filter == 'all':
        orders = conn.execute('''
                              SELECT o.*, u.username
                              FROM orders o
                                       JOIN users u ON o.user_id = u.id
                              ORDER BY o.created_at DESC
                              ''').fetchall()
    else:
        orders = conn.execute('''
                              SELECT o.*, u.username
                              FROM orders o
                                       JOIN users u ON o.user_id = u.id
                              WHERE o.status = ?
                              ORDER BY o.created_at DESC
                              ''', (status_filter,)).fetchall()

    conn.close()

    return render_template('admin/orders.html', orders=orders, status_filter=status_filter)


@app.route('/admin/orders/<int:order_id>')
@login_required
def admin_order_detail(order_id):
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    order = conn.execute('''
                         SELECT o.*, u.username, u.email
                         FROM orders o
                                  JOIN users u ON o.user_id = u.id
                         WHERE o.id = ?
                         ''', (order_id,)).fetchone()

    if not order:
        flash('❌ Order not found', 'error')
        conn.close()
        return redirect('/admin/orders')

    order_items = conn.execute('''
                               SELECT oi.*, p.image_url
                               FROM order_items oi
                                        LEFT JOIN products p ON oi.product_id = p.id
                               WHERE oi.order_id = ?
                               ''', (order_id,)).fetchall()

    conn.close()

    return render_template('admin/order_detail.html', order=order, order_items=order_items)


@app.route('/admin/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
def admin_update_order_status(order_id):
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    new_status = request.form.get('status')

    conn = get_db_connection()
    try:
        conn.execute('''
                     UPDATE orders
                     SET status     = ?,
                         updated_at = CURRENT_TIMESTAMP
                     WHERE id = ?
                     ''', (new_status, order_id))
        conn.commit()
        flash(f'✅ Order status updated to {new_status}', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'❌ Error updating order status: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(f'/admin/orders/{order_id}')


@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    users = conn.execute('''
                         SELECT u.*,
                                COUNT(o.id)                      as order_count,
                                COALESCE(SUM(o.total_amount), 0) as total_spent
                         FROM users u
                                  LEFT JOIN orders o ON u.id = o.user_id
                         GROUP BY u.id
                         ORDER BY u.created_at DESC
                         ''').fetchall()
    conn.close()

    return render_template('admin/users.html', users=users)


@app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
def admin_toggle_admin(user_id):
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user:
        flash('❌ User not found', 'error')
        conn.close()
        return redirect('/admin/users')

    new_admin_status = not bool(user['is_admin'])

    try:
        conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_admin_status, user_id))
        conn.commit()
        action = "granted" if new_admin_status else "revoked"
        flash(f'✅ Admin privileges {action} for user {user["username"]}', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'❌ Error updating user: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect('/admin/users')


@app.route('/admin/analytics')
@login_required
def admin_analytics():
    if not current_user.is_admin:
        flash('❌ Access denied. Admin privileges required.', 'error')
        return redirect('/')

    conn = get_db_connection()

    # Sales overview
    total_sales = \
        conn.execute('SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status = "completed"').fetchone()[0]
    total_orders = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    avg_order_value = \
        conn.execute('SELECT COALESCE(AVG(total_amount), 0) FROM orders WHERE status = "completed"').fetchone()[0]

    # Monthly sales
    monthly_sales = conn.execute('''
                                 SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as order_count,
               SUM(total_amount) as revenue
                                 FROM orders
                                 WHERE status = 'completed'
                                 GROUP BY strftime('%Y-%m', created_at)
                                 ORDER BY month DESC
                                     LIMIT 12
                                 ''').fetchall()

    # Top products
    top_products = conn.execute('''
                                SELECT p.name,
                                       p.id,
                                       SUM(oi.quantity)    as total_sold,
                                       SUM(oi.total_price) as revenue
                                FROM order_items oi
                                         JOIN products p ON oi.product_id = p.id
                                         JOIN orders o ON oi.order_id = o.id
                                WHERE o.status = 'completed'
                                GROUP BY p.id
                                ORDER BY total_sold DESC LIMIT 10
                                ''').fetchall()

    # Order status distribution
    status_distribution = conn.execute('''
                                       SELECT status, COUNT(*) as count
                                       FROM orders
                                       GROUP BY status
                                       ''').fetchall()

    conn.close()

    return render_template('admin/analytics.html',
                           total_sales=total_sales,
                           total_orders=total_orders,
                           avg_order_value=avg_order_value,
                           monthly_sales=monthly_sales,
                           top_products=top_products,
                           status_distribution=status_distribution)


# =============================================
# REGULAR ROUTES
# =============================================

@app.route('/')
def index():
    conn = get_db_connection()

    # Get featured products with optional rating info
    featured_products = conn.execute('''
                                     SELECT p.*, c.name as category_name
                                     FROM products p
                                              LEFT JOIN categories c ON p.category_id = c.id LIMIT 4
                                     ''').fetchall()

    # Convert to list of dictionaries and add ratings
    featured_products_list = []
    for product in featured_products:
        product_dict = row_to_dict(product)

        rating_result = conn.execute('''
                                     SELECT COALESCE(AVG(rating), 0) as average_rating, COUNT(*) as review_count
                                     FROM reviews
                                     WHERE product_id = ?
                                       AND status = 'approved'
                                     ''', (product_dict['id'],)).fetchone()

        product_dict['average_rating'] = rating_result['average_rating'] if rating_result else 0
        product_dict['review_count'] = rating_result['review_count'] if rating_result else 0
        featured_products_list.append(product_dict)

    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()

    return render_template('index.html', products=featured_products_list, categories=categories)


@app.route('/products')
def products_page():
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'name')
    sort_order = request.args.get('sort_order', 'asc')

    conn = get_db_connection()

    # Build base query with sorting
    query = '''
            SELECT p.*, \
                   c.name                     as category_name, \
                   c.slug                     as category_slug,
                   COALESCE(AVG(r.rating), 0) as average_rating,
                   COUNT(r.id)                as review_count
            FROM products p
                     LEFT JOIN categories c ON p.category_id = c.id
                     LEFT JOIN reviews r ON p.id = r.product_id AND r.status = 'approved'
            WHERE 1 = 1 \
            '''
    params = []

    if category_id:
        query += ' AND p.category_id = ?'
        params.append(category_id)

    if search_query:
        query += ' AND (p.name LIKE ? OR p.description LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])

    query += ' GROUP BY p.id, c.name, c.slug'

    # Apply sorting
    sort_options = {
        'name': 'p.name',
        'price': 'p.price',
        'rating': 'average_rating',
        'date': 'p.created_at'
    }

    if sort_by in sort_options:
        # For date, default to newest first (descending)
        if sort_by == 'date' and sort_order == 'asc':
            query += f' ORDER BY {sort_options[sort_by]} ASC'
        elif sort_by == 'date' and sort_order == 'desc':
            query += f' ORDER BY {sort_options[sort_by]} DESC'
        else:
            query += f' ORDER BY {sort_options[sort_by]} {sort_order.upper()}'
    else:
        query += ' ORDER BY p.created_at DESC'

    products = conn.execute(query, params).fetchall()

    # Convert to list of dictionaries
    products_list = []
    for product in products:
        product_dict = row_to_dict(product)
        product_dict['average_rating'] = float(product['average_rating']) if product['average_rating'] else 0.0
        product_dict['review_count'] = product['review_count']
        products_list.append(product_dict)

    categories = conn.execute('SELECT * FROM categories').fetchall()
    current_category = None

    if category_id:
        current_category = conn.execute('SELECT * FROM categories WHERE id = ?', (category_id,)).fetchone()

    # Get price range
    price_range = conn.execute('''
                               SELECT MIN(price) as min_price, MAX(price) as max_price
                               FROM products
                               ''').fetchone()

    conn.close()

    return render_template('products.html',
                           products=products_list,
                           categories=categories,
                           current_category=current_category,
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           price_range=price_range)


@app.route('/advanced-search')
def advanced_search():
    # Get all filter parameters with defaults
    search_query = request.args.get('q', '')
    category_id = request.args.get('category', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    sort_by = request.args.get('sort_by', 'name')
    sort_order = request.args.get('sort_order', 'asc')
    in_stock = request.args.get('in_stock', type=bool)

    conn = get_db_connection()

    # Build base query
    query = '''
            SELECT p.*, \
                   c.name                     as category_name, \
                   c.slug                     as category_slug,
                   COALESCE(AVG(r.rating), 0) as average_rating,
                   COUNT(r.id)                as review_count
            FROM products p
                     LEFT JOIN categories c ON p.category_id = c.id
                     LEFT JOIN reviews r ON p.id = r.product_id AND r.status = 'approved'
            WHERE 1 = 1 \
            '''
    params = []

    # Apply filters
    if search_query:
        query += ' AND (p.name LIKE ? OR p.description LIKE ? OR c.name LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

    if category_id:
        query += ' AND p.category_id = ?'
        params.append(category_id)

    if min_price is not None:
        query += ' AND p.price >= ?'
        params.append(min_price)

    if max_price is not None:
        query += ' AND p.price <= ?'
        params.append(max_price)

    if in_stock:
        query += ' AND p.stock > 0'

    # Group by for ratings
    query += ' GROUP BY p.id, c.name, c.slug'

    # Apply sorting
    sort_options = {
        'name': 'p.name',
        'price': 'p.price',
        'rating': 'average_rating',
        'date': 'p.created_at',
        'reviews': 'review_count'
    }

    if sort_by in sort_options:
        sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'
        # Special handling for date (newest first by default)
        if sort_by == 'date' and sort_order == 'asc':
            sort_direction = 'ASC'
        elif sort_by == 'date' and sort_order == 'desc':
            sort_direction = 'DESC'
        query += f' ORDER BY {sort_options[sort_by]} {sort_direction}'
    else:
        query += ' ORDER BY p.created_at DESC'

    # Execute query
    products = conn.execute(query, params).fetchall()

    # Convert to list of dictionaries
    products_list = []
    for product in products:
        product_dict = row_to_dict(product)
        product_dict['average_rating'] = float(product['average_rating']) if product['average_rating'] else 0.0
        product_dict['review_count'] = product['review_count']
        products_list.append(product_dict)

    categories = conn.execute('SELECT * FROM categories').fetchall()

    # Get price range for filter
    price_range = conn.execute('''
                               SELECT MIN(price) as min_price, MAX(price) as max_price
                               FROM products
                               ''').fetchone()

    conn.close()

    return render_template('advanced_search.html',
                           products=products_list,
                           categories=categories,
                           search_query=search_query,
                           selected_category=category_id,
                           min_price=min_price,
                           max_price=max_price,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           in_stock=in_stock,
                           price_range=price_range)


@app.route('/category/<slug>')
def category_page(slug):
    conn = get_db_connection()

    category = conn.execute('SELECT * FROM categories WHERE slug = ?', (slug,)).fetchone()
    if not category:
        flash('Category not found', 'error')
        return redirect(url_for('products_page'))

    # Get products without complex joins
    products = conn.execute('''
                            SELECT p.*, c.name as category_name, c.slug as category_slug
                            FROM products p
                                     LEFT JOIN categories c ON p.category_id = c.id
                            WHERE p.category_id = ?
                            ORDER BY p.created_at DESC
                            ''', (category['id'],)).fetchall()

    # Convert to list of dictionaries and add ratings
    products_list = []
    for product in products:
        product_dict = row_to_dict(product)

        rating_result = conn.execute('''
                                     SELECT COALESCE(AVG(rating), 0) as average_rating, COUNT(*) as review_count
                                     FROM reviews
                                     WHERE product_id = ?
                                       AND status = 'approved'
                                     ''', (product_dict['id'],)).fetchone()

        product_dict['average_rating'] = rating_result['average_rating'] if rating_result else 0
        product_dict['review_count'] = rating_result['review_count'] if rating_result else 0
        products_list.append(product_dict)

    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()

    return render_template('category.html',
                           products=products_list,
                           categories=categories,
                           current_category=category)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()

    # Get product details
    product = conn.execute('''
                           SELECT p.*, c.name as category_name
                           FROM products p
                                    LEFT JOIN categories c ON p.category_id = c.id
                           WHERE p.id = ?
                           ''', (product_id,)).fetchone()

    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('products_page'))

    # Convert product to dictionary and add ratings
    product_dict = row_to_dict(product)

    rating_result = conn.execute('''
                                 SELECT COALESCE(AVG(rating), 0) as average_rating, COUNT(*) as review_count
                                 FROM reviews
                                 WHERE product_id = ?
                                   AND status = 'approved'
                                 ''', (product_id,)).fetchone()

    product_dict['average_rating'] = rating_result['average_rating'] if rating_result else 0
    product_dict['review_count'] = rating_result['review_count'] if rating_result else 0

    # Get approved reviews for this product
    reviews = conn.execute('''
                           SELECT r.*, u.username
                           FROM reviews r
                                    JOIN users u ON r.user_id = u.id
                           WHERE r.product_id = ?
                             AND r.status = 'approved'
                           ORDER BY r.created_at DESC LIMIT 10
                           ''', (product_id,)).fetchall()

    # Get related products
    related_products = conn.execute('''
                                    SELECT p.*, c.name as category_name
                                    FROM products p
                                             LEFT JOIN categories c ON p.category_id = c.id
                                    WHERE p.category_id = ?
                                      AND p.id != ?
        LIMIT 4
                                    ''', (product_dict['category_id'], product_id)).fetchall()

    # Convert related products to list of dictionaries and add ratings
    related_products_list = []
    for related_product in related_products:
        related_product_dict = row_to_dict(related_product)

        related_rating_result = conn.execute('''
                                             SELECT COALESCE(AVG(rating), 0) as average_rating, COUNT(*) as review_count
                                             FROM reviews
                                             WHERE product_id = ?
                                               AND status = 'approved'
                                             ''', (related_product_dict['id'],)).fetchone()

        related_product_dict['average_rating'] = related_rating_result['average_rating'] if related_rating_result else 0
        related_product_dict['review_count'] = related_rating_result['review_count'] if related_rating_result else 0
        related_products_list.append(related_product_dict)

    # Check if user has already reviewed this product
    user_review = None
    if current_user.is_authenticated:
        user_review = conn.execute('''
                                   SELECT *
                                   FROM reviews
                                   WHERE product_id = ?
                                     AND user_id = ?
                                   ''', (product_id, current_user.id)).fetchone()

    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()

    return render_template('product_detail.html',
                           product=product_dict,
                           reviews=reviews,
                           related_products=related_products_list,
                           categories=categories,
                           user_review=user_review)


@app.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    rating = request.form.get('rating', type=int)
    title = request.form.get('title', '').strip()
    comment = request.form.get('comment', '').strip()

    # Validate input
    if not rating or rating < 1 or rating > 5:
        flash('Please select a valid rating between 1 and 5 stars', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    if not title or not comment:
        flash('Please provide both a title and comment for your review', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    conn = get_db_connection()

    # Check if product exists
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        flash('Product not found', 'error')
        conn.close()
        return redirect(url_for('products_page'))

    # Check if user has already reviewed this product
    existing_review = conn.execute('''
                                   SELECT *
                                   FROM reviews
                                   WHERE product_id = ?
                                     AND user_id = ?
                                   ''', (product_id, current_user.id)).fetchone()

    if existing_review:
        flash('You have already reviewed this product', 'error')
        conn.close()
        return redirect(url_for('product_detail', product_id=product_id))

    # Insert new review
    conn.execute('''
                 INSERT INTO reviews (product_id, user_id, rating, title, comment, status)
                 VALUES (?, ?, ?, ?, ?, 'pending')
                 ''', (product_id, current_user.id, rating, title, comment))

    conn.commit()
    conn.close()

    flash('✅ Thank you for your review! It will be visible after approval.', 'success')
    return redirect(url_for('product_detail', product_id=product_id))


@app.route('/cart')
@login_required
def cart():
    # Get cart items from database for logged-in users
    conn = get_db_connection()
    cart_items_db = conn.execute('''
                                 SELECT cart_items.*, products.name, products.price, products.image_url
                                 FROM cart_items
                                          JOIN products ON cart_items.product_id = products.id
                                 WHERE cart_items.user_id = ?
                                 ''', (current_user.id,)).fetchall()
    conn.close()

    # Convert to list of dictionaries for template
    cart_items = []
    for item in cart_items_db:
        cart_items.append({
            'product_id': item['product_id'],
            'name': item['name'],
            'price': item['price'],
            'image_url': item['image_url'],
            'quantity': item['quantity']
        })

    # For debugging - show what's in localStorage vs database
    print(f"🛒 Database cart has {len(cart_items)} items for user {current_user.id}")

    return render_template('cart.html', cart_items=cart_items)

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    # Get cart items from database
    conn = get_db_connection()
    cart_items_db = conn.execute('''
                                 SELECT cart_items.*, products.name, products.price, products.image_url
                                 FROM cart_items
                                          JOIN products ON cart_items.product_id = products.id
                                 WHERE cart_items.user_id = ?
                                 ''', (current_user.id,)).fetchall()
    conn.close()

    # Convert to list of dictionaries
    cart_items = []
    for item in cart_items_db:
        cart_items.append({
            'product_id': item['product_id'],
            'name': item['name'],
            'price': item['price'],
            'image_url': item['image_url'],
            'quantity': item['quantity']
        })

    # If no items in database, show helpful message
    if not cart_items:
        return render_template('checkout_empty.html', username=current_user.username)

    if request.method == 'POST':
        # Process checkout
        shipping_address = request.form.get('shipping_address', '123 Main St, City, State 12345')
        billing_address = request.form.get('billing_address', '123 Main St, City, State 12345')
        payment_method = request.form.get('payment_method', 'credit_card')

        try:
            # Create order
            order_id, order_number = Order.create_order(
                current_user.id,
                cart_items,
                shipping_address,
                billing_address,
                payment_method
            )

            flash(f'✅ Order #{order_number} placed successfully!', 'success')
            return redirect(f'/order-confirmation/{order_id}')

        except Exception as e:
            flash('❌ Error processing your order. Please try again.', 'error')
            print(f"Order error: {e}")

    return render_template('checkout.html', cart_items=cart_items)


@app.route('/order-confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    order, order_items = Order.get_order_details(order_id)

    # Verify order belongs to current user
    if not order or order['user_id'] != current_user.id:
        flash('❌ Order not found', 'error')
        return redirect('/')

    return render_template('order_confirmation.html', order=order, order_items=order_items)


@app.route('/orders')
@login_required
def order_history():
    orders = Order.get_user_orders(current_user.id)
    return render_template('order_history.html', orders=orders)


@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    order, order_items = Order.get_order_details(order_id)

    # Verify order belongs to current user
    if not order or order['user_id'] != current_user.id:
        flash('❌ Order not found', 'error')
        return redirect('/orders')

    return render_template('order_details.html', order=order, order_items=order_items)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.find_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('✅ Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect('/')
        else:
            flash('❌ Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if len(password) < 6:
            flash('❌ Password must be at least 6 characters long', 'error')
            return render_template('register.html')

        conn = get_db_connection()
        try:
            password_hash = generate_password_hash(password)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, email, password_hash, is_admin) VALUES (?, ?, ?, ?)',
                           (username, email, password_hash, 0))
            user_id = cursor.lastrowid
            conn.commit()

            # Log the user in after registration
            user = User(id=user_id, username=username, email=email,
                        password_hash=password_hash, created_at=datetime.now(), is_admin=False)
            login_user(user)

            flash('✅ Registration successful! Welcome!', 'success')
            return redirect('/')
        except sqlite3.IntegrityError:
            flash('❌ Username or email already exists!', 'error')
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Logged out successfully!', 'success')
    return redirect('/')


# API Routes for Cart
@app.route('/api/cart', methods=['GET'])
@login_required
def get_cart():
    conn = get_db_connection()
    cart_items = conn.execute('''
                              SELECT cart_items.*, products.name, products.price, products.image_url
                              FROM cart_items
                                       JOIN products ON cart_items.product_id = products.id
                              WHERE cart_items.user_id = ?
                              ''', (current_user.id,)).fetchall()
    conn.close()

    cart_data = []
    for item in cart_items:
        cart_data.append({
            'id': item['id'],
            'product_id': item['product_id'],
            'name': item['name'],
            'price': item['price'],
            'image_url': item['image_url'],
            'quantity': item['quantity']
        })

    return jsonify(cart_data)


@app.route('/api/cart', methods=['POST'])
@login_required
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    conn = get_db_connection()

    # Check if product exists
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404

    # Check if item already in cart
    existing_item = conn.execute(
        'SELECT * FROM cart_items WHERE user_id = ? AND product_id = ?',
        (current_user.id, product_id)
    ).fetchone()

    if existing_item:
        # Update quantity
        conn.execute(
            'UPDATE cart_items SET quantity = quantity + ? WHERE user_id = ? AND product_id = ?',
            (quantity, current_user.id, product_id)
        )
    else:
        # Add new item
        conn.execute(
            'INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)',
            (current_user.id, product_id, quantity)
        )

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Item added to cart'})


@app.route('/api/cart/<int:product_id>', methods=['DELETE'])
@login_required
def remove_from_cart(product_id):
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM cart_items WHERE user_id = ? AND product_id = ?',
        (current_user.id, product_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Item removed from cart'})


@app.route('/api/cart/<int:product_id>', methods=['PUT'])
@login_required
def update_cart_quantity(product_id):
    data = request.get_json()
    quantity = data.get('quantity')

    if quantity <= 0:
        return remove_from_cart(product_id)

    conn = get_db_connection()
    conn.execute(
        'UPDATE cart_items SET quantity = ? WHERE user_id = ? AND product_id = ?',
        (quantity, current_user.id, product_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Cart updated'})


@app.route('/api/cart/clear', methods=['DELETE'])
@login_required
def clear_cart():
    conn = get_db_connection()
    conn.execute('DELETE FROM cart_items WHERE user_id = ?', (current_user.id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Cart cleared'})


@app.route('/api/products')
def api_products():
    conn = get_db_connection()
    products = conn.execute('''
                            SELECT p.*,
                                   c.name                     as category_name,
                                   COALESCE(AVG(r.rating), 0) as average_rating,
                                   COUNT(r.id)                as review_count
                            FROM products p
                                     LEFT JOIN categories c ON p.category_id = c.id
                                     LEFT JOIN reviews r ON p.id = r.product_id AND r.status = 'approved'
                            GROUP BY p.id
                            ''').fetchall()
    conn.close()

    products_list = []
    for product in products:
        products_list.append({
            'id': product['id'],
            'name': product['name'],
            'price': product['price'],
            'description': product['description'],
            'image_url': product['image_url'],
            'category': product['category_name'],
            'category_id': product['category_id'],
            'stock': product['stock'],
            'average_rating': product['average_rating'],
            'review_count': product['review_count']
        })

    return jsonify(products_list)


@app.route('/api/categories')
def api_categories():
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories').fetchall()
    conn.close()

    categories_list = []
    for category in categories:
        categories_list.append({
            'id': category['id'],
            'name': category['name'],
            'slug': category['slug'],
            'description': category['description']
        })

    return jsonify(categories_list)


@app.route('/api/reviews/<int:product_id>')
def api_reviews(product_id):
    conn = get_db_connection()
    reviews = conn.execute('''
                           SELECT r.*, u.username
                           FROM reviews r
                                    JOIN users u ON r.user_id = u.id
                           WHERE r.product_id = ?
                             AND r.status = 'approved'
                           ORDER BY r.created_at DESC
                           ''', (product_id,)).fetchall()
    conn.close()

    reviews_list = []
    for review in reviews:
        reviews_list.append({
            'id': review['id'],
            'product_id': review['product_id'],
            'user_id': review['user_id'],
            'username': review['username'],
            'rating': review['rating'],
            'title': review['title'],
            'comment': review['comment'],
            'created_at': review['created_at']
        })

    return jsonify(reviews_list)


# Search Suggestions API
@app.route('/api/search/suggestions')
def search_suggestions():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])

    conn = get_db_connection()

    # Search in product names and categories
    suggestions = conn.execute('''
                               SELECT p.name    as product_name,
                                      c.name    as category_name,
                                      p.id      as product_id,
                                      c.id      as category_id,
                                      'product' as type
                               FROM products p
                                        LEFT JOIN categories c ON p.category_id = c.id
                               WHERE p.name LIKE ?
                                  OR c.name LIKE ? LIMIT 10
                               ''', (f'%{query}%', f'%{query}%')).fetchall()

    conn.close()

    results = []
    for suggestion in suggestions:
        results.append({
            'type': suggestion['type'],
            'product_name': suggestion['product_name'],
            'category_name': suggestion['category_name'],
            'product_id': suggestion['product_id'],
            'category_id': suggestion['category_id'],
            'display_text': f"{suggestion['product_name']} ({suggestion['category_name']})"
        })

    return jsonify(results)


# Admin routes for review moderation
@app.route('/admin/reviews')
@login_required
def admin_reviews():
    # Use proper admin check
    if not current_user.is_admin:
        flash('❌ Access denied', 'error')
        return redirect('/')

    conn = get_db_connection()
    pending_reviews = conn.execute('''
                                   SELECT r.*, u.username, p.name as product_name
                                   FROM reviews r
                                            JOIN users u ON r.user_id = u.id
                                            JOIN products p ON r.product_id = p.id
                                   WHERE r.status = 'pending'
                                   ORDER BY r.created_at DESC
                                   ''').fetchall()

    approved_reviews = conn.execute('''
                                    SELECT r.*, u.username, p.name as product_name
                                    FROM reviews r
                                             JOIN users u ON r.user_id = u.id
                                             JOIN products p ON r.product_id = p.id
                                    WHERE r.status = 'approved'
                                    ORDER BY r.created_at DESC LIMIT 50
                                    ''').fetchall()

    conn.close()

    return render_template('admin_reviews.html',
                           pending_reviews=pending_reviews,
                           approved_reviews=approved_reviews)


@app.route('/admin/reviews/<int:review_id>/<action>')
@login_required
def moderate_review(review_id, action):
    if not current_user.is_admin:
        flash('❌ Access denied', 'error')
        return redirect('/')

    if action not in ['approve', 'reject']:
        flash('❌ Invalid action', 'error')
        return redirect('/admin/reviews')

    conn = get_db_connection()

    if action == 'approve':
        conn.execute('UPDATE reviews SET status = "approved" WHERE id = ?', (review_id,))
        flash('✅ Review approved successfully', 'success')
    else:
        conn.execute('UPDATE reviews SET status = "rejected" WHERE id = ?', (review_id,))
        flash('✅ Review rejected successfully', 'success')

    conn.commit()
    conn.close()

    return redirect('/admin/reviews')


# User profile route
@app.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    user_reviews = conn.execute('''
                                SELECT r.*, p.name as product_name, p.image_url
                                FROM reviews r
                                         JOIN products p ON r.product_id = p.id
                                WHERE r.user_id = ?
                                ORDER BY r.created_at DESC
                                ''', (current_user.id,)).fetchall()
    conn.close()

    return render_template('profile.html', user_reviews=user_reviews)


# Address Management Routes
@app.route('/addresses')
@login_required
def addresses():
    shipping_addresses = Address.get_user_addresses(current_user.id, 'shipping')
    billing_addresses = Address.get_user_addresses(current_user.id, 'billing')
    return render_template('addresses.html',
                           shipping_addresses=shipping_addresses,
                           billing_addresses=billing_addresses)


@app.route('/address/add', methods=['GET', 'POST'])
@login_required
def add_address():
    if request.method == 'POST':
        address_type = request.form.get('address_type')
        full_name = request.form.get('full_name')
        street_address = request.form.get('street_address')
        city = request.form.get('city')
        state = request.form.get('state')
        postal_code = request.form.get('postal_code')
        country = request.form.get('country', 'US')
        phone_number = request.form.get('phone_number')
        is_default = request.form.get('is_default') == 'on'

        try:
            Address.create_address(
                current_user.id, address_type, full_name, street_address,
                city, state, postal_code, country, phone_number, is_default
            )
            flash('✅ Address added successfully!', 'success')
            return redirect('/addresses')
        except Exception as e:
            flash('❌ Error adding address', 'error')

    return render_template('add_address.html')


# Debug routes
@app.route('/debug/cart')
@login_required
def debug_cart():
    """Check what's in the database cart"""
    conn = get_db_connection()
    cart_items = conn.execute('''
                              SELECT cart_items.*, products.name, products.price
                              FROM cart_items
                                       JOIN products ON cart_items.product_id = products.id
                              WHERE cart_items.user_id = ?
                              ''', (current_user.id,)).fetchall()
    conn.close()

    result = {
        'user_id': current_user.id,
        'username': current_user.username,
        'cart_items_count': len(cart_items),
        'cart_items': [dict(item) for item in cart_items]
    }

    return jsonify(result)


@app.route('/debug/localstorage')
def debug_localstorage():
    """Check what's in localStorage (client-side)"""
    return '''
    <html>
    <body>
        <h1>LocalStorage Debug</h1>
        <div id="localStorageContent"></div>
        <script>
            const cart = JSON.parse(localStorage.getItem('cart')) || [];
            document.getElementById('localStorageContent').innerHTML = 
                '<h3>Cart items in localStorage:</h3>' + 
                '<pre>' + JSON.stringify(cart, null, 2) + '</pre>' +
                '<p>Item count: ' + cart.length + '</p>';
        </script>
    </body>
    </html>
    '''


@app.route('/debug/sync-cart', methods=['POST'])
@login_required
def debug_sync_cart():
    """Force sync localStorage to database"""
    cart_data = request.get_json()

    if not cart_data:
        return jsonify({'error': 'No cart data provided'}), 400

    conn = get_db_connection()

    try:
        # Clear existing cart
        conn.execute('DELETE FROM cart_items WHERE user_id = ?', (current_user.id,))

        # Add new items
        for item in cart_data:
            conn.execute(
                'INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)',
                (current_user.id, item['product_id'], item['quantity'])
            )

        conn.commit()
        return jsonify({'success': True, 'message': f'Synced {len(cart_data)} items to database'})

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500

    finally:
        conn.close()


@app.route('/force-checkout')
@login_required
def force_checkout():
    """Force checkout by syncing localStorage to database first"""
    return '''
    <html>
    <body>
        <h1>Force Checkout</h1>
        <p>This will sync your localStorage cart to the database and redirect to checkout.</p>
        <button onclick="syncAndCheckout()">Sync Cart & Checkout</button>
        <div id="result"></div>

        <script>
            async function syncAndCheckout() {
                const cart = JSON.parse(localStorage.getItem('cart')) || [];
                if (cart.length === 0) {
                    alert('Your cart is empty!');
                    return;
                }

                document.getElementById('result').innerHTML = 'Syncing cart...';

                try {
                    // Sync to database
                    const response = await fetch('/debug/sync-cart', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(cart)
                    });

                    const result = await response.json();

                    if (result.success) {
                        document.getElementById('result').innerHTML = '✓ ' + result.message;
                        // Redirect to checkout
                        setTimeout(() => {
                            window.location.href = '/checkout';
                        }, 1000);
                    } else {
                        document.getElementById('result').innerHTML = '✗ Error: ' + result.error;
                    }
                } catch (error) {
                    document.getElementById('result').innerHTML = '✗ Network error: ' + error;
                }
            }

            // Show current cart
            const cart = JSON.parse(localStorage.getItem('cart')) || [];
            document.getElementById('result').innerHTML = 
                '<h3>Current Cart:</h3><pre>' + JSON.stringify(cart, null, 2) + '</pre>';
        </script>
    </body>
    </html>
    '''


# =============================================
# WISHLIST ROUTES
# =============================================

@app.route('/wishlist')
@login_required
def wishlist():
    # Get user's default wishlist
    wishlist = Wishlist.get_user_wishlist(current_user.id)
    items = Wishlist.get_wishlist_items(wishlist['id'])

    return render_template('wishlist.html',
                           wishlist=wishlist,
                           wishlist_items=items)


@app.route('/wishlist/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    wishlist = Wishlist.get_user_wishlist(current_user.id)

    # Check if product exists
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()

    if not product:
        flash('❌ Product not found', 'error')
        return redirect(request.referrer or url_for('products_page'))

    # Add to wishlist
    success = Wishlist.add_to_wishlist(wishlist['id'], product_id)

    if success:
        flash('✅ Product added to wishlist!', 'success')
    else:
        flash('ℹ️ Product is already in your wishlist', 'info')

    return redirect(request.referrer or url_for('products_page'))


@app.route('/wishlist/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_wishlist(product_id):
    wishlist = Wishlist.get_user_wishlist(current_user.id)
    Wishlist.remove_from_wishlist(wishlist['id'], product_id)

    flash('✅ Product removed from wishlist', 'success')
    return redirect(request.referrer or url_for('wishlist'))


@app.route('/wishlist/move-to-cart/<int:product_id>', methods=['POST'])
@login_required
def move_wishlist_to_cart(product_id):
    wishlist = Wishlist.get_user_wishlist(current_user.id)

    # Check if product is in wishlist
    if not Wishlist.is_in_wishlist(wishlist['id'], product_id):
        flash('❌ Product not found in wishlist', 'error')
        return redirect(url_for('wishlist'))

    # Add to cart
    try:
        response = add_to_cart_internal(current_user.id, product_id, 1)
        if response['success']:
            # Remove from wishlist
            Wishlist.remove_from_wishlist(wishlist['id'], product_id)
            flash('✅ Product moved to cart!', 'success')
        else:
            flash('❌ Failed to add product to cart', 'error')
    except Exception as e:
        flash('❌ Error moving product to cart', 'error')

    return redirect(url_for('wishlist'))


@app.route('/wishlist/move-all-to-cart', methods=['POST'])
@login_required
def move_all_wishlist_to_cart():
    wishlist = Wishlist.get_user_wishlist(current_user.id)
    items = Wishlist.get_wishlist_items(wishlist['id'])

    moved_count = 0
    for item in items:
        try:
            response = add_to_cart_internal(current_user.id, item['product_id'], 1)
            if response['success']:
                Wishlist.remove_from_wishlist(wishlist['id'], item['product_id'])
                moved_count += 1
        except:
            continue

    if moved_count > 0:
        flash(f'✅ {moved_count} products moved to cart!', 'success')
    else:
        flash('❌ No products could be moved to cart', 'error')

    return redirect(url_for('wishlist'))


@app.route('/wishlist/public')
def public_wishlists():
    wishlists = Wishlist.get_public_wishlists()
    return render_template('public_wishlists.html', wishlists=wishlists)


@app.route('/wishlist/share/<int:wishlist_id>')
def view_shared_wishlist(wishlist_id):
    wishlist = Wishlist.get_wishlist_by_id(wishlist_id)

    if not wishlist or not wishlist['is_public']:
        flash('❌ Wishlist not found or is private', 'error')
        return redirect(url_for('public_wishlists'))

    items = Wishlist.get_wishlist_items(wishlist_id)
    return render_template('shared_wishlist.html',
                           wishlist=wishlist,
                           items=items)


@app.route('/wishlist/toggle-visibility', methods=['POST'])
@login_required
def toggle_wishlist_visibility():
    wishlist = Wishlist.get_user_wishlist(current_user.id)

    conn = get_db_connection()
    new_visibility = not bool(wishlist['is_public'])
    conn.execute(
        'UPDATE wishlists SET is_public = ? WHERE id = ?',
        (new_visibility, wishlist['id'])
    )
    conn.commit()
    conn.close()

    status = "public" if new_visibility else "private"
    flash(f'✅ Wishlist is now {status}', 'success')
    return redirect(url_for('wishlist'))


# Helper function for internal cart operations
def add_to_cart_internal(user_id, product_id, quantity):
    conn = get_db_connection()

    # Check if product exists
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        conn.close()
        return {'success': False, 'error': 'Product not found'}

    # Check if item already in cart
    existing_item = conn.execute(
        'SELECT * FROM cart_items WHERE user_id = ? AND product_id = ?',
        (user_id, product_id)
    ).fetchone()

    if existing_item:
        # Update quantity
        conn.execute(
            'UPDATE cart_items SET quantity = quantity + ? WHERE user_id = ? AND product_id = ?',
            (quantity, user_id, product_id)
        )
    else:
        # Add new item
        conn.execute(
            'INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)',
            (user_id, product_id, quantity)
        )

    conn.commit()
    conn.close()

    # Update localStorage
    update_localstorage_cart(user_id)

    return {'success': True}


def update_localstorage_cart(user_id):
    """Update localStorage cart after server changes"""
    # This would typically be handled by the frontend
    # For now, we'll just note that the cart was updated
    pass



# Debug: Check for duplicate route names
print("🔍 Checking for duplicate route endpoints...")
endpoints = {}
for rule in app.url_map.iter_rules():
    if rule.endpoint in endpoints:
        print(f"❌ DUPLICATE: {rule.endpoint}")
        print(f"   Route 1: {endpoints[rule.endpoint]}")
        print(f"   Route 2: {rule}")
    else:
        endpoints[rule.endpoint] = str(rule)

print(f"✅ Total unique endpoints: {len(endpoints)}")

if __name__ == '__main__':
    # Print debug information
    print("=" * 60)
    print("🚀 E-commerce Website Starting...")
    print("📁 Current working directory:", os.getcwd())
    print("📁 Template folder:", TEMPLATE_DIR)
    print("📁 Static folder:", STATIC_DIR)
    print("✅ Template folder exists:", os.path.exists(TEMPLATE_DIR))
    print("✅ Static folder exists:", os.path.exists(STATIC_DIR))

    if os.path.exists(TEMPLATE_DIR):
        print("📄 Files in template folder:")
        for file in os.listdir(TEMPLATE_DIR):
            print("   └──", file)

    # Initialize database - THIS IS THE FIX!
    init_database()

    print("\n🔑 Demo credentials:")
    print("   Username: demo")
    print("   Password: demo123")
    print("   Admin access:")
    print("   Username: admin")
    print("   Password: admin123")
    print("\n🌐 Access the site at: http://localhost:5000")
    print("   Admin dashboard: http://localhost:5000/admin")
    print("   Admin reviews: http://localhost:5000/admin/reviews")
    print("   Advanced Search: http://localhost:5000/advanced-search")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)