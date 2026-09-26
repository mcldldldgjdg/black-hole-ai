from aiohttp import web
import os

async def handle_static(request):
    file_path = os.path.join('.', request.path.lstrip('/'))
    if os.path.isfile(file_path):
        return web.FileResponse(file_path)
    return web.Response(status=404, text='Not found')

app = web.Application()
app.router.add_get('/{filename:.*}', handle_static)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=3000)
