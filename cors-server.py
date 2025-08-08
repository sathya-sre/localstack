#!/usr/bin/env python3
"""
CORS-enabled proxy server for LocalStack dashboard
Handles CORS issues by proxying requests to LocalStack
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError
import os

PORT = 9999
LOCALSTACK_URL = 'http://localhost:4566'

class CORSProxyHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/api/'):
            # Proxy request to LocalStack
            self.proxy_to_localstack()
        elif self.path == '/logs':
            # Handle logs request
            self.handle_logs_request()
        elif self.path == '/' or self.path == '/dashboard':
            # Serve dashboard
            self.serve_dashboard()
        else:
            # Serve static files
            super().do_GET()

    def do_POST(self):
        if self.path == '/test':
            # Handle demo test requests
            self.handle_demo_test()
        elif self.path.startswith('/api/'):
            # Proxy POST requests to LocalStack
            self.proxy_to_localstack()
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = json.dumps({'error': 'Endpoint not found'})
            self.wfile.write(error_response.encode())

    def proxy_to_localstack(self):
        """Proxy requests to LocalStack with CORS headers"""
        try:
            # Remove /api prefix and forward to LocalStack
            localstack_path = self.path[4:]  # Remove '/api'
            url = f"{LOCALSTACK_URL}{localstack_path}"
            
            print(f"🔄 Proxying: {self.path} -> {url}")
            
            # Make request to LocalStack
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                
                # Send successful response with CORS headers
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)
                
        except HTTPError as e:
            print(f"❌ HTTP Error {e.code}: {e.reason}")
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = json.dumps({'error': f'HTTP {e.code}: {e.reason}'})
            self.wfile.write(error_response.encode())
            
        except URLError as e:
            print(f"❌ Connection Error: {e.reason}")
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = json.dumps({'error': f'LocalStack connection failed: {e.reason}'})
            self.wfile.write(error_response.encode())
            
        except Exception as e:
            print(f"❌ Proxy Error: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_response = json.dumps({'error': f'Proxy error: {str(e)}'})
            self.wfile.write(error_response.encode())

    def serve_dashboard(self):
        """Serve the dashboard HTML"""
        try:
            with open('dashboard.html', 'r') as f:
                content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Dashboard not found</h1>')

    def handle_demo_test(self):
        """Handle demo test execution"""
        try:
            # Get request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            if post_data:
                request_data = json.loads(post_data.decode())
                service_type = request_data.get('service', 'all')
            else:
                service_type = 'all'
            
            print(f"🧪 Running demo for service: {service_type}")
            
            # Execute demo script
            import subprocess
            import sys
            
            result = subprocess.run([
                sys.executable, 'demo.py'
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                
                output = f"✅ Demo completed successfully!\n\n{result.stdout}"
                if result.stderr:
                    output += f"\n\nWarnings:\n{result.stderr}"
                
                self.wfile.write(output.encode())
                print("✅ Demo completed successfully")
            else:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                
                error_output = f"❌ Demo failed!\n\nError:\n{result.stderr}\n\nOutput:\n{result.stdout}"
                self.wfile.write(error_output.encode())
                print(f"❌ Demo failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.send_response(408)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Demo execution timed out after 60 seconds")
            print("⏰ Demo execution timed out")
            
        except Exception as e:
            print(f"❌ Demo handler error: {e}")
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            error_msg = f"Demo execution error: {str(e)}"
            self.wfile.write(error_msg.encode())

    def handle_logs_request(self):
        """Handle logs request - fetch LocalStack logs"""
        try:
            import subprocess
            import datetime
            
            # Try multiple possible container names
            container_names = [
                'localstack-main',
                'localstack-demo-localstack-1', 
                'localstack_main',
                'localstack'
            ]
            
            logs_data = None
            used_container = None
            
            for container_name in container_names:
                try:
                    # Try to get Docker logs from LocalStack container
                    result = subprocess.run([
                        'docker', 'logs', '--tail', '100', '--timestamps', container_name
                    ], capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        logs_data = result.stdout
                        used_container = container_name
                        print(f"📋 Successfully got logs from container: {container_name}")
                        break
                        
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    continue
            
            if logs_data:
                # Parse Docker logs into structured format
                logs = []
                for line in logs_data.strip().split('\n'):
                    if line.strip():
                        # Try to parse timestamp from Docker format
                        try:
                            if 'T' in line and 'Z' in line:
                                # Docker timestamp format: 2024-08-08T10:30:45.123456789Z
                                parts = line.split(' ', 1)
                                if len(parts) >= 2:
                                    timestamp = parts[0].replace('T', ' ').replace('Z', '')
                                    message = parts[1]
                                    
                                    # Determine log level
                                    level = 'info'
                                    message_upper = message.upper()
                                    if any(keyword in message_upper for keyword in ['ERROR', 'EXCEPTION', 'FAILED', 'FATAL']):
                                        level = 'error'
                                    elif any(keyword in message_upper for keyword in ['WARN', 'WARNING']):
                                        level = 'warning'
                                    elif any(keyword in message_upper for keyword in ['DEBUG']):
                                        level = 'debug'
                                    elif any(keyword in message_upper for keyword in ['STARTED', 'READY', 'SUCCESS', 'RUNNING']):
                                        level = 'info'
                                    
                                    logs.append({
                                        'timestamp': timestamp,
                                        'level': level,
                                        'message': message[:800]  # Limit message length
                                    })
                            else:
                                # Fallback for lines without timestamp
                                logs.append({
                                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'level': 'info',
                                    'message': line[:800]
                                })
                        except Exception:
                            # Fallback for parsing issues
                            logs.append({
                                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'level': 'info',
                                'message': line[:800]
                            })
                
                response_data = {
                    'success': True,
                    'logs': logs[-50:],  # Return last 50 logs
                    'total': len(logs),
                    'source': f'docker:{used_container}',
                    'container': used_container
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                
                print(f"📋 Served {len(logs[-50:])} log entries from {used_container}")
                
            else:
                # Fallback if no container logs available
                print("📋 No LocalStack container found, providing troubleshooting info")
                
                # Get list of running containers for troubleshooting
                try:
                    ps_result = subprocess.run(['docker', 'ps', '--format', 'table {{.Names}}\t{{.Image}}\t{{.Status}}'], 
                                             capture_output=True, text=True, timeout=10)
                    container_list = ps_result.stdout if ps_result.returncode == 0 else "Unable to list containers"
                except:
                    container_list = "Docker not available"
                
                troubleshoot_logs = [
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'level': 'warning',
                        'message': 'No LocalStack container found running'
                    },
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'level': 'info', 
                        'message': f'Searched for containers: {", ".join(container_names)}'
                    },
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'level': 'info',
                        'message': 'Available containers:'
                    },
                    {
                        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'level': 'debug',
                        'message': container_list[:500]
                    }
                ]
                
                response_data = {
                    'success': True,
                    'logs': troubleshoot_logs,
                    'total': len(troubleshoot_logs),
                    'source': 'troubleshooting'
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                
        except Exception as e:
            print(f"❌ Logs handler error: {e}")
            error_response = {
                'success': False,
                'error': f'Failed to fetch logs: {str(e)}',
                'logs': [{
                    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'level': 'error',
                    'message': f'Error fetching logs: {str(e)}'
                }]
            }
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Try to bind to the port with better error handling
    try:
        with socketserver.TCPServer(("", PORT), CORSProxyHandler) as httpd:
            # Allow reuse of the address to prevent "Address already in use" errors
            httpd.allow_reuse_address = True
            
            print(f"🚀 LocalStack CORS Proxy Server starting at http://localhost:{PORT}")
            print(f"📊 Dashboard: http://localhost:{PORT}/")
            print(f"🔄 Proxy: http://localhost:{PORT}/api/* -> http://localhost:4566/*")
            print(f"⚡ LocalStack: http://localhost:4566")
            print("Press Ctrl+C to stop")
            
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n👋 Server stopped")
                
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"❌ Error: Port {PORT} is already in use!")
            print("💡 Try these solutions:")
            print(f"   • Kill existing process: lsof -ti :{PORT} | xargs kill -9")
            print(f"   • Use a different port: Change PORT in {__file__}")
            print("   • Wait a moment and try again")
        else:
            print(f"❌ Network error: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
