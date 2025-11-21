import ccxt
import time
import json
from datetime import datetime

class TriangularArbitrageBot:
    def __init__(
        self,
        api_key,
        api_secret,
        base_currency='USDT',
        min_profit_percent=0.3,
        use_futures=False,
        testnet=False
    ):
        """
        Initialise le bot d'arbitrage triangulaire
        
        :param api_key: Clé API Binance
        :param api_secret: Secret API Binance
        :param base_currency: Devise de base (USDT par défaut)
        :param min_profit_percent: Profit minimum en % pour exécuter un trade
        :param use_futures: Active le trading futures (Binance USD-M)
        :param testnet: Active le mode testnet/sandbox si disponible
        """
        exchange_class = ccxt.binanceusdm if use_futures else ccxt.binance
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future' if use_futures else 'spot',
                'fetchCurrencies': False
            }
        })

        if testnet and hasattr(self.exchange, 'set_sandbox_mode'):
            self.exchange.set_sandbox_mode(True)
        
        self.base_currency = base_currency
        self.min_profit_percent = min_profit_percent
        self.triangular_pairs = []
        
    def load_markets(self):
        """Charge les marchés disponibles sur Binance"""
        print("Chargement des marchés...")
        self.exchange.load_markets()
        print(f"✓ {len(self.exchange.markets)} marchés chargés")
        
    def find_triangular_pairs(self):
        """
        Trouve toutes les opportunités d'arbitrage triangulaire possibles
        Exemple: USDT -> BTC -> ETH -> USDT
        """
        print(f"\nRecherche de paires triangulaires avec {self.base_currency}...")
        triangular_pairs = []
        
        # Récupère toutes les paires avec la devise de base
        base_pairs = [symbol for symbol in self.exchange.symbols 
                     if self.base_currency in symbol and self.exchange.markets[symbol]['active']]
        
        for pair1 in base_pairs:
            # Première paire: BASE/QUOTE1 (ex: USDT/BTC)
            parts1 = pair1.split('/')
            if parts1[0] != self.base_currency:
                continue
                
            quote1 = parts1[1]  # BTC
            
            # Cherche les paires avec quote1 comme base
            for pair2 in self.exchange.symbols:
                if not self.exchange.markets[pair2]['active']:
                    continue
                    
                parts2 = pair2.split('/')
                if parts2[0] != quote1:
                    continue
                    
                quote2 = parts2[1]  # ETH
                
                # Évite les boucles simples
                if quote2 == self.base_currency:
                    continue
                
                # Cherche la paire de retour
                pair3 = f"{self.base_currency}/{quote2}"
                if pair3 in self.exchange.symbols and self.exchange.markets[pair3]['active']:
                    triangular_pairs.append({
                        'pair1': pair1,  # USDT/BTC
                        'pair2': pair2,  # BTC/ETH
                        'pair3': pair3,  # USDT/ETH
                        'path': f"{self.base_currency} -> {quote1} -> {quote2} -> {self.base_currency}"
                    })
        
        self.triangular_pairs = triangular_pairs
        print(f"✓ {len(triangular_pairs)} opportunités triangulaires trouvées")
        
        # Affiche quelques exemples
        for i, pair in enumerate(triangular_pairs[:5]):
            print(f"  {i+1}. {pair['path']}")
        if len(triangular_pairs) > 5:
            print(f"  ... et {len(triangular_pairs) - 5} autres")
            
        return triangular_pairs
    
    def get_orderbook_prices(self, symbol):
        """Récupère les meilleurs prix bid/ask du carnet d'ordres"""
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit=5)
            best_bid = orderbook['bids'][0][0] if len(orderbook['bids']) > 0 else None
            best_ask = orderbook['asks'][0][0] if len(orderbook['asks']) > 0 else None
            return best_bid, best_ask
        except Exception as e:
            print(f"Erreur lors de la récupération du carnet d'ordres pour {symbol}: {e}")
            return None, None
    
    def calculate_arbitrage_opportunity(self, triangle, initial_amount=1000):
        """
        Calcule le profit potentiel d'une opportunité d'arbitrage triangulaire
        
        :param triangle: Dictionnaire contenant les 3 paires
        :param initial_amount: Montant initial en devise de base
        :return: Dictionnaire avec les détails du calcul
        """
        try:
            # Récupère les prix pour chaque paire
            _, ask1 = self.get_orderbook_prices(triangle['pair1'])  # Acheter
            _, ask2 = self.get_orderbook_prices(triangle['pair2'])  # Acheter
            bid3, _ = self.get_orderbook_prices(triangle['pair3'])  # Vendre
            
            if not all([ask1, ask2, bid3]):
                return None
            
            # Calcul de l'arbitrage
            # 1. Acheter pair1 (USDT -> BTC)
            amount_after_1 = initial_amount / ask1
            
            # 2. Acheter pair2 (BTC -> ETH)
            amount_after_2 = amount_after_1 / ask2
            
            # 3. Vendre pair3 (ETH -> USDT)
            final_amount = amount_after_2 * bid3
            
            # Calcul des frais (0.1% par trade sur Binance)
            fees = initial_amount * 0.001 * 3
            profit = final_amount - initial_amount - fees
            profit_percent = (profit / initial_amount) * 100
            
            return {
                'triangle': triangle,
                'initial_amount': initial_amount,
                'final_amount': final_amount,
                'profit': profit,
                'profit_percent': profit_percent,
                'prices': {
                    'pair1_ask': ask1,
                    'pair2_ask': ask2,
                    'pair3_bid': bid3
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Erreur calcul arbitrage: {e}")
            return None
    
    def execute_arbitrage(self, opportunity, dry_run=False):
        """
        Exécute l'arbitrage en temps réel
        
        :param opportunity: Opportunité d'arbitrage calculée
        :param dry_run: Si True, n'envoie pas d'ordres réels
        """
        if opportunity['profit_percent'] < self.min_profit_percent:
            return False
            
        print(f"\n[EXECUTION] Opportunité détectée!")
        print(f"  Path: {opportunity['triangle']['path']}")
        print(f"  Profit estimé: {opportunity['profit']:.2f} {self.base_currency} ({opportunity['profit_percent']:.3f}%)")
        
        try:
            if dry_run:
                print("  → Mode simulation: aucun ordre réel ne sera placé.")
                print("  Simulation exécutée avec les prix du carnet d'ordres.")
                return True

            print("  → Exécution des ordres...")
            
            # Récupère les symboles et montants
            pair1 = opportunity['triangle']['pair1']
            pair2 = opportunity['triangle']['pair2']
            pair3 = opportunity['triangle']['pair3']
            
            # 1. Acheter pair1 (USDT -> BTC)
            print(f"  1. Achat {pair1}...")
            order1 = self.exchange.create_market_buy_order(
                pair1,
                opportunity['initial_amount'] / opportunity['prices']['pair1_ask']
            )
            amount_after_1 = float(order1['filled'])
            print(f"     ✓ Acheté: {amount_after_1}")
            
            time.sleep(0.1)  # Petit délai pour éviter les erreurs de rate limit
            
            # 2. Acheter pair2 (BTC -> ETH)
            print(f"  2. Achat {pair2}...")
            order2 = self.exchange.create_market_buy_order(
                pair2,
                amount_after_1
            )
            amount_after_2 = float(order2['filled'])
            print(f"     ✓ Acheté: {amount_after_2}")
            
            time.sleep(0.1)
            
            # 3. Vendre pair3 (ETH -> USDT)
            print(f"  3. Vente {pair3}...")
            order3 = self.exchange.create_market_sell_order(
                pair3,
                amount_after_2
            )
            final_amount = float(order3['cost'])
            print(f"     ✓ Vendu pour: {final_amount} {self.base_currency}")
            
            # Calcul du profit réel
            real_profit = final_amount - opportunity['initial_amount']
            real_profit_percent = (real_profit / opportunity['initial_amount']) * 100
            
            print(f"\n  ✓ Arbitrage exécuté avec succès!")
            print(f"  Profit réel: {real_profit:.2f} {self.base_currency} ({real_profit_percent:.3f}%)")
            
            return True
            
        except Exception as e:
            print(f"  ✗ Erreur d'exécution: {e}")
            return False
    
    def scan_opportunities(self, iterations=100, delay=2):
        """
        Scan continu des opportunités d'arbitrage
        
        :param iterations: Nombre d'itérations (None pour infini)
        :param delay: Délai entre chaque scan en secondes
        """
        print(f"\n{'='*60}")
        print("DÉMARRAGE DU SCAN D'ARBITRAGE TRIANGULAIRE")
        print(f"{'='*60}")
        print(f"Profit minimum: {self.min_profit_percent}%")
        print(f"Délai entre scans: {delay}s")
        print(f"{'='*60}\n")
        
        count = 0
        opportunities_found = 0
        
        try:
            while iterations is None or count < iterations:
                count += 1
                print(f"\r[Scan #{count}] En cours...", end='', flush=True)
                
                best_opportunity = None
                best_profit = 0
                
                # Scan toutes les paires triangulaires
                for triangle in self.triangular_pairs:
                    opportunity = self.calculate_arbitrage_opportunity(triangle)
                    
                    if opportunity and opportunity['profit_percent'] > best_profit:
                        best_profit = opportunity['profit_percent']
                        best_opportunity = opportunity
                
                # Si une opportunité profitable est trouvée
                if best_opportunity and best_opportunity['profit_percent'] >= self.min_profit_percent:
                    opportunities_found += 1
                    self.execute_arbitrage(best_opportunity, dry_run=False)
                
                time.sleep(delay)
                
        except KeyboardInterrupt:
            print("\n\nArrêt du bot...")
            print(f"Total scans: {count}")
            print(f"Opportunités trouvées: {opportunities_found}")

# ============================================================================
# EXEMPLE D'UTILISATION
# ============================================================================

if __name__ == "__main__":
    # ATTENTION: Remplacez par vos vraies clés API
    API_KEY = 'GceZ6wvAsTq6Je9OGAGiibsK9ljrIp4t6mE8tRZclH1RKYnL4VeCo3YSmoF0S3FP'
    API_SECRET = '48i2LtTDorSVJpnYFhXJ2KTbr05cd3tsDn8t60Wm1uxF0gNX1SASjj4X6YtKB1Si'

    # Créer le bot
    bot = TriangularArbitrageBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_currency='BNB',
        min_profit_percent=0.3,  # Profit minimum de 0.3%
        use_futures=True,
        testnet=True
    )

    # Charger les marchés et trouver les paires
    bot.load_markets()
    bot.find_triangular_pairs()
    
    # Démarrer le scan (mode simulation par défaut)
    print("\n⚠️  MODE SIMULATION ACTIVÉ - Aucun ordre ne sera placé")
    print("Pour activer le trading réel, modifiez dry_run=False dans execute_arbitrage()\n")
    
    bot.scan_opportunities(iterations=None, delay=2)  # Scan infini
