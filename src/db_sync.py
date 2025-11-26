#!/usr/bin/env python3
"""
Multi-Environment Database Sync
Synchronizes schema and data with automatic masking
"""

import psycopg2
import hashlib
import random
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class DatabaseSync:
    
    def __init__(self):
        self.prod_conn = None
        self.dev_conn = None
        self.masking_rules = {}
        
    def connect_all(self):
        try:
            self.prod_conn = psycopg2.connect(
                host='localhost', port=5456,
                dbname='prod_db', user='postgres', password='postgres'
            )
            self.prod_conn.autocommit = True
            
            self.dev_conn = psycopg2.connect(
                host='localhost', port=5457,
                dbname='dev_db', user='postgres', password='postgres'
            )
            self.dev_conn.autocommit = True
            
            logger.info("Connected to production and development databases")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def setup_prod_data(self):
        """Setup production database with sensitive data"""
        
        logger.info("Setting up production database...")
        
        cursor = self.prod_conn.cursor()
        cursor.execute("""
            DROP TABLE IF EXISTS customers CASCADE;
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS payments CASCADE;
            
            CREATE TABLE customers (
                customer_id SERIAL PRIMARY KEY,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                email VARCHAR(100),
                phone VARCHAR(20),
                ssn VARCHAR(11),
                credit_card VARCHAR(16),
                address TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE TABLE orders (
                order_id SERIAL PRIMARY KEY,
                customer_id INT REFERENCES customers(customer_id),
                order_total DECIMAL(10,2),
                order_date TIMESTAMP DEFAULT NOW(),
                status VARCHAR(20)
            );
            
            CREATE TABLE payments (
                payment_id SERIAL PRIMARY KEY,
                order_id INT REFERENCES orders(order_id),
                payment_method VARCHAR(50),
                amount DECIMAL(10,2),
                transaction_id VARCHAR(100)
            );
            
            INSERT INTO customers (first_name, last_name, email, phone, ssn, credit_card, address)
            VALUES 
                ('John', 'Doe', 'john.doe@email.com', '555-0100', '123-45-6789', '4532123456789012', '123 Main St, City, ST 12345'),
                ('Jane', 'Smith', 'jane.smith@email.com', '555-0200', '987-65-4321', '5412345678901234', '456 Oak Ave, Town, ST 54321'),
                ('Bob', 'Johnson', 'bob.j@email.com', '555-0300', '456-78-9012', '4916123456789012', '789 Pine Rd, Village, ST 67890');
            
            INSERT INTO orders (customer_id, order_total, status)
            VALUES 
                (1, 299.99, 'completed'),
                (2, 149.50, 'completed'),
                (3, 599.00, 'pending');
            
            INSERT INTO payments (order_id, payment_method, amount, transaction_id)
            VALUES 
                (1, 'credit_card', 299.99, 'TXN-ABC123'),
                (2, 'credit_card', 149.50, 'TXN-DEF456');
        """)
        cursor.close()
        
        logger.info("✓ Production data created (3 customers, 3 orders)")
    
    def define_masking_rules(self):
        """Define data masking rules for sensitive fields"""
        
        self.masking_rules = {
            'customers': {
                'email': self.mask_email,
                'phone': self.mask_phone,
                'ssn': self.mask_ssn,
                'credit_card': self.mask_credit_card,
                'address': self.mask_address
            },
            'payments': {
                'transaction_id': self.mask_transaction_id
            }
        }
        
        logger.info("Masking rules defined for sensitive fields")
    
    def mask_email(self, email: str) -> str:
        """Mask email address"""
        if '@' in email:
            local, domain = email.split('@', 1)
            return f"{local[:2]}***@{domain}"
        return "masked@example.com"
    
    def mask_phone(self, phone: str) -> str:
        """Mask phone number"""
        return "555-XXXX"
    
    def mask_ssn(self, ssn: str) -> str:
        """Mask social security number"""
        return "XXX-XX-" + ssn[-4:] if len(ssn) >= 4 else "XXX-XX-XXXX"
    
    def mask_credit_card(self, cc: str) -> str:
        """Mask credit card number"""
        return "****-****-****-" + cc[-4:] if len(cc) >= 4 else "****-****-****-XXXX"
    
    def mask_address(self, address: str) -> str:
        """Mask address"""
        return "REDACTED ADDRESS"
    
    def mask_transaction_id(self, txn_id: str) -> str:
        """Mask transaction ID"""
        return "TXN-" + hashlib.md5(txn_id.encode()).hexdigest()[:8].upper()
    
    def sync_schema(self):
        """Synchronize schema from prod to dev"""
        
        logger.info("Synchronizing schema from PROD to DEV...")
        
        prod_cursor = self.prod_conn.cursor()
        dev_cursor = self.dev_conn.cursor()
        
        # Get table definitions from prod
        prod_cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        tables = [row[0] for row in prod_cursor.fetchall()]
        
        for table in tables:
            # Get CREATE TABLE statement
            prod_cursor.execute(f"""
                SELECT column_name, data_type, character_maximum_length,
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            
            columns = prod_cursor.fetchall()
            
            # Drop and recreate in dev
            dev_cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            
            col_defs = []
            for col_name, data_type, max_len, nullable, default in columns:
                col_def = f"{col_name} "
                
                if data_type == 'character varying':
                    col_def += f"VARCHAR({max_len})" if max_len else "VARCHAR"
                elif data_type == 'integer':
                    col_def += "INT"
                elif data_type == 'numeric':
                    col_def += "DECIMAL(10,2)"
                elif data_type == 'timestamp without time zone':
                    col_def += "TIMESTAMP"
                else:
                    col_def += data_type.upper()
                
                if nullable == 'NO':
                    col_def += " NOT NULL"
                
                if default:
                    if 'nextval' in default:
                        col_def = f"{col_name} SERIAL PRIMARY KEY"
                    elif default != 'NULL':
                        col_def += f" DEFAULT {default}"
                
                col_defs.append(col_def)
            
            create_sql = f"CREATE TABLE {table} ({', '.join(col_defs)})"
            dev_cursor.execute(create_sql)
            
            logger.info(f"  ✓ Synced table: {table}")
        
        prod_cursor.close()
        dev_cursor.close()
        
        logger.info("✓ Schema synchronization complete")
    
    def sync_data_with_masking(self):
        """Sync data with automatic masking of sensitive fields"""
        
        logger.info("Synchronizing data with masking from PROD to DEV...")
        
        prod_cursor = self.prod_conn.cursor()
        dev_cursor = self.dev_conn.cursor()
        
        tables = ['customers', 'orders', 'payments']
        
        for table in tables:
            logger.info(f"  Syncing table: {table}")
            
            # Get all data from prod
            prod_cursor.execute(f"SELECT * FROM {table}")
            columns = [desc[0] for desc in prod_cursor.description]
            rows = prod_cursor.fetchall()
            
            # Clear dev table
            dev_cursor.execute(f"DELETE FROM {table}")
            
            # Get masking rules for this table
            table_rules = self.masking_rules.get(table, {})
            
            # --- NEW: fetch column types for this table from information_schema ---
            prod_cursor.execute("""
                SELECT column_name, data_type, 
                       COALESCE(character_maximum_length::text, '') AS character_maximum_length
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            schema_info = prod_cursor.fetchall()
            # Build a map: column_name -> (data_type, character_maximum_length)
            column_types = {col: (dtype, int(max_len) if max_len != '' else None)
                            for col, dtype, max_len in schema_info}
            
            masked_count = 0
            
            for row in rows:
                # Apply masking
                masked_row = list(row)
                
                for i, col_name in enumerate(columns):
                    if col_name in table_rules:
                        original_value = masked_row[i]
                        if original_value is not None:
                            masked_row[i] = table_rules[col_name](str(original_value))
                            masked_count += 1
                
                # Insert into dev (apply truncation according to column types)
                placeholders = ','.join(['%s'] * len(masked_row))
                
                safe_row = []
                for i, value in enumerate(masked_row):
                    if value is None:
                        safe_row.append(value)
                        continue

                    col_name = columns[i]
                    dtype, max_len = column_types.get(col_name, (None, None))

                    # Only enforce truncation for character varying columns with a max length
                    if dtype == 'character varying' and max_len:
                        if isinstance(value, str) and len(value) > max_len:
                            logger.warning(
                                f"Truncating value for column '{col_name}' "
                                f"from length {len(value)} → {max_len}"
                            )
                            value = value[:max_len]

                    # If target column is TEXT or other, no truncation needed
                    safe_row.append(value)

                dev_cursor.execute(
                    f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                    safe_row
                )
            
            logger.info(f"    ✓ Copied {len(rows)} rows ({masked_count} fields masked)")
        
        prod_cursor.close()
        dev_cursor.close()
        
        logger.info("✓ Data synchronization complete")
    
    def compare_data(self):
        """Compare data between prod and dev to show masking"""
        
        print("\n" + "=" * 80)
        print("DATA COMPARISON: Production vs Development")
        print("=" * 80)
        
        prod_cursor = self.prod_conn.cursor()
        dev_cursor = self.dev_conn.cursor()
        
        # Compare customers table
        prod_cursor.execute("SELECT first_name, email, phone, ssn, credit_card FROM customers LIMIT 2")
        prod_data = prod_cursor.fetchall()
        
        dev_cursor.execute("SELECT first_name, email, phone, ssn, credit_card FROM customers LIMIT 2")
        dev_data = dev_cursor.fetchall()
        
        for i, (prod_row, dev_row) in enumerate(zip(prod_data, dev_data), 1):
            print(f"\nCustomer {i}:")
            print(f"  PRODUCTION:")
            print(f"    Name: {prod_row[0]}")
            print(f"    Email: {prod_row[1]}")
            print(f"    Phone: {prod_row[2]}")
            print(f"    SSN: {prod_row[3]}")
            print(f"    Credit Card: {prod_row[4]}")
            
            print(f"  DEVELOPMENT (Masked):")
            print(f"    Name: {dev_row[0]}")
            print(f"    Email: {dev_row[1]}")
            print(f"    Phone: {dev_row[2]}")
            print(f"    SSN: {dev_row[3]}")
            print(f"    Credit Card: {dev_row[4]}")
        
        prod_cursor.close()
        dev_cursor.close()
        
        print("=" * 80)
    
    def validate_sync(self):
        """Validate that sync was successful"""
        
        logger.info("Validating synchronization...")
        
        prod_cursor = self.prod_conn.cursor()
        dev_cursor = self.dev_conn.cursor()
        
        validation_passed = True
        
        # Check table count
        prod_cursor.execute("SELECT COUNT(*) FROM customers")
        prod_count = prod_cursor.fetchone()[0]
        
        dev_cursor.execute("SELECT COUNT(*) FROM customers")
        dev_count = dev_cursor.fetchone()[0]
        
        if prod_count == dev_count:
            logger.info(f"  ✓ Row count matches: {prod_count} rows")
        else:
            logger.error(f"  ✗ Row count mismatch: PROD={prod_count}, DEV={dev_count}")
            validation_passed = False
        
        # Check that sensitive data is masked
        dev_cursor.execute("SELECT email, ssn FROM customers LIMIT 1")
        email, ssn = dev_cursor.fetchone()
        
        if '***' in email and 'XXX' in ssn:
            logger.info("  ✓ Sensitive data is properly masked")
        else:
            logger.error("  ✗ Sensitive data not masked properly")
            validation_passed = False
        
        prod_cursor.close()
        dev_cursor.close()
        
        if validation_passed:
            logger.info("✓ Validation passed")
        else:
            logger.error("✗ Validation failed")
        
        return validation_passed
    
    def run_demo(self):
        """Run database sync demo"""
        
        print("\n" + "=" * 80)
        print("MULTI-ENVIRONMENT DATABASE SYNC")
        print("=" * 80)
        
        if not self.connect_all():
            return
        
        print("\nPHASE 1: Setup Production Data")
        print("-" * 80)
        self.setup_prod_data()
        
        print("\nPHASE 2: Define Masking Rules")
        print("-" * 80)
        self.define_masking_rules()
        
        print("\nPHASE 3: Synchronize Schema")
        print("-" * 80)
        self.sync_schema()
        
        print("\nPHASE 4: Sync Data with Masking")
        print("-" * 80)
        self.sync_data_with_masking()
        
        print("\nPHASE 5: Compare Prod vs Dev")
        self.compare_data()
        
        print("\nPHASE 6: Validate Sync")
        print("-" * 80)
        self.validate_sync()
        
        print("\n" + "=" * 80)
        print("Key Features:")
        print("  - Automated schema synchronization")
        print("  - Data masking for sensitive fields")
        print("  - PII protection (email, SSN, credit cards)")
        print("  - Validation and compliance checks")
        print("=" * 80)


def main():
    sync = DatabaseSync()
    sync.run_demo()


if __name__ == "__main__":
    main()
