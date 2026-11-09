"""Loopback-only gallery with allowlisted source files and byte-range video seeking."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import argparse, json, mimetypes, os, re, sys
from library import BASE, STUDIO, catalog, entry_map, reference_brief, context_handoff, site_settings, ui_language, set_ui_language, ui_motion, set_ui_motion, welcome_seen, set_welcome_seen
from project_index import public_index, get_file, get_asset, get_asset_poster, starter_request_text
from review_actions import apply_decision, ReviewError
from security import registered_file, MEDIA, NOTES
from reference_intake import save as save_reference, current as reference_state, visibility_state, set_visibility, IntakeError
from feedback import save as save_feedback, current as feedback_state, save_link as save_feedback_link, change as change_feedback, FeedbackError
from reference_notes import save as save_reference_note, current as reference_notes_state, handoff as reference_handoff, NoteError
from reference_preview import save as save_reference_preview, PreviewError
from project_tools import state as project_tools_state, open_editor, ToolsError

from project_script import current as script_state, save as save_script
from scripting import brief_current, brief_save, script_ready, voice_current, voice_save, voice_remember, voice_forget, hooks_current, hooks_save, hook_apply, feedback_current as script_feedback_current, feedback_save as script_feedback_save
from new_project import create as create_new_video, NewProjectError
from materials import save_upload as upload_material, list as list_materials, update as update_material, add_from_library, list_library, file_path as material_file_path, poster_path as material_poster_path, MaterialsError
from looks import list as list_looks, file_path as look_file_path, LookError
from choices import current as choices_current, save as save_choices, ChoicesError
from effects import list as list_effects
import claude_runner
import server_messages
from addons import state as addons_state, save as save_addons, AddonsError
import inspiration

class Handler(SimpleHTTPRequestHandler):
    def trusted(self, write=False):
        hosts = self.headers.get_all('Host', [])
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if len(hosts) != 1 or hosts[0] not in allowed:
            self.send_error(403); return False
        origin = self.headers.get('Origin')
        if (self.headers.get('Sec-Fetch-Site') == 'cross-site' or
                (origin is not None and origin != 'http://' + hosts[0]) or
                (write and origin != 'http://' + hosts[0])):
            self.send_error(403); return False
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        super().end_headers()

    def do_POST(self):
        if self.path in {'/script-brief', '/script-ready', '/writing-voice', '/writing-memory', '/writing-memory-forget', '/script-hooks', '/script-hook', '/script-feedback'}:
            if not self.trusted(write=True): return
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1: return self.send_error(400)
            if self.headers.get('X-Studio-Action') != self.path[1:]: return self.send_error(403)
            if self.headers.get_content_type() != 'application/json': return self.send_error(415)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 262144: return self.send_error(413)
                body = json.loads(self.rfile.read(size))
                action = {'/script-brief': brief_save, '/script-ready': script_ready, '/writing-voice': voice_save, '/script-hooks': hooks_save,
                          '/writing-memory': voice_remember, '/writing-memory-forget': voice_forget,
                          '/script-hook': hook_apply, '/script-feedback': script_feedback_save}[self.path]
                result = action(body)
            except json.JSONDecodeError: return self.json_error(400, 'Use a valid writing request.')
            except (FeedbackError, ReviewError) as error: return self.json_error(error.status, str(error))
            except (OSError, ValueError, TypeError, KeyError): return self.json_error(503, 'Writing context could not be saved. Your existing files and draft are preserved.')
            return self.text(json.dumps(result), 'application/json', False)
        if self.path == '/project-script':
            raw=self.json_request('project-script',262144)
            if raw is None:return
            try:
                result=save_script(json.loads(raw))
            except json.JSONDecodeError:return self.json_error(400,'Use a valid script save request.')
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The script could not be saved. Existing scripts and your draft are preserved.')
            return self.text(json.dumps(result),'application/json',False)

        if self.path in {'/reference-preview','/open-editor'}:
            if not self.trusted(write=True):return
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:return self.send_error(400)
            action='reference-preview' if self.path=='/reference-preview' else 'open-editor'
            if self.headers.get('X-Studio-Action')!=action:return self.send_error(403)
            if self.headers.get_content_type()!='application/json':return self.send_error(415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:return self.send_error(413)
                body=json.loads(self.rfile.read(size))
                result=save_reference_preview(body) if action=='reference-preview' else open_editor(body)
            except json.JSONDecodeError:return self.json_error(400,'Use a valid studio request.')
            except (PreviewError,IntakeError,ToolsError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'This action is unavailable. Your saved work is preserved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path in {'/reference-notes','/reference-handoff'}:
            if not self.trusted(write=True):return
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:return self.send_error(400)
            action='reference-note' if self.path=='/reference-notes' else 'reference-handoff'
            if self.headers.get('X-Studio-Action')!=action:return self.send_error(403)
            if self.headers.get_content_type()!='application/json':return self.send_error(415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=(16384 if action=='reference-note' else 262144):return self.send_error(413)
                body=json.loads(self.rfile.read(size))
                result=save_reference_note(body) if action=='reference-note' else reference_handoff(body,'http://'+self.headers['Host'])
            except json.JSONDecodeError:return self.json_error(400,'Use a valid reference note request.')
            except (NoteError,FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Reference notes are unavailable. Existing notes and your draft are preserved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/reference-visibility':
            raw=self.json_request('reference-visibility',4096)
            if raw is None:return
            try:
                result=set_visibility(json.loads(raw))
            except json.JSONDecodeError:return self.json_error(400,'Use a valid library request.')
            except (IntakeError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The library could not be changed. Your references are preserved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/ui-language':
            raw=self.json_request('ui-language',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'language'}:raise ValueError()
                result=set_ui_language(body['language'])
            except json.JSONDecodeError:return self.json_error(400,'Use a valid language request.')
            except (ValueError,TypeError,KeyError):return self.json_error(400,'Choose he or en.')
            except OSError:return self.json_error(503,'The language setting could not be saved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/ui-motion':
            raw=self.json_request('ui-motion',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'motion'}:raise ValueError()
                result=set_ui_motion(body['motion'])
            except json.JSONDecodeError:return self.json_error(400,'Use a valid motion request.')
            except (ValueError,TypeError,KeyError):return self.json_error(400,'Choose auto, always or off.')
            except OSError:return self.json_error(503,'The motion setting could not be saved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/ui-welcome':
            raw=self.json_request('ui-welcome',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'welcome_seen'}:raise ValueError()
                result=set_welcome_seen(body['welcome_seen'])
            except json.JSONDecodeError:return self.json_error(400,'Use a valid welcome request.')
            except (ValueError,TypeError,KeyError):return self.json_error(400,'Send welcome_seen: true.')
            except OSError:return self.json_error(503,'The welcome setting could not be saved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/addons':
            raw=self.json_request('addons',4096)
            if raw is None:return
            try:
                result=save_addons(json.loads(raw))
            except json.JSONDecodeError:return self.json_error(400,'Use a valid add-ons request.')
            except AddonsError as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Add-ons could not be saved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/new-video':
            raw=self.json_request('new-video',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                result=create_new_video(body)
            except json.JSONDecodeError:return self.json_error(400,'newVideo.error.invalidRequest')
            except NewProjectError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'newVideo.error.filesystem')
            return self.text(json.dumps(result),'application/json',False,201)
        if self.path == '/material-update':
            raw=self.json_request('material-update',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)-{'project','item','tag','note','owned'} or 'project' not in body or 'item' not in body:raise ValueError()
                patch={k:v for k,v in body.items() if k in ('tag','note','owned')}
                result=update_material(body['project'],body['item'],patch)
            except json.JSONDecodeError:return self.json_error(400,'materials.error.invalidRequest')
            except MaterialsError as error:return self.json_error(error.status,error.message_key)
            except (ValueError,TypeError,KeyError):return self.json_error(400,'materials.error.invalidRequest')
            except OSError:return self.json_error(503,'materials.error.filesystem')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/choices':
            raw=self.json_request('choices',16384)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or 'project' not in body:raise ValueError()
                # 'seq' is stripped (never forwarded to save_choices) rather than rejected as
                # an unknown field, so a browser tab still holding the fix-round-1 bundle
                # (which sent one) keeps working during a rollout instead of hitting a 400.
                patch={k:v for k,v in body.items() if k not in ('project','seq')}
                result=save_choices(body['project'],patch)
            except json.JSONDecodeError:return self.json_error(400,'choices.error.invalidRequest')
            except ChoicesError as error:return self.json_error(error.status,error.message_key)
            except (ValueError,TypeError,KeyError):return self.json_error(400,'choices.error.invalidRequest')
            except OSError:return self.json_error(503,'choices.error.filesystem')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/material-from-library':
            raw=self.json_request('material-from-library',4096)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'project','item'}:raise ValueError()
                result=add_from_library(body['project'],body['item'])
            except json.JSONDecodeError:return self.json_error(400,'materials.error.invalidRequest')
            except MaterialsError as error:return self.json_error(error.status,error.message_key)
            except (ValueError,TypeError,KeyError):return self.json_error(400,'materials.error.invalidRequest')
            except OSError:return self.json_error(503,'materials.error.filesystem')
            return self.text(json.dumps(result),'application/json',False,201)
        if self.path == '/style-card':
            raw=self.json_request('style-card',131072)
            if raw is None:return
            try:
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'reference','text','pinned','revision'}:raise ValueError()
                if body['revision'] is not None and not isinstance(body['revision'],str):raise ValueError()
                result=inspiration.save_card(body['reference'],body['text'],body['pinned'],body['revision'])
            except json.JSONDecodeError:return self.json_error(400,'inspiration.error.invalidRequest')
            except inspiration.InspirationError as error:return self.json_error(error.status,error.message_key,error.details)
            except (ValueError,TypeError,KeyError):return self.json_error(400,'inspiration.error.invalidRequest')
            except OSError:return self.json_error(503,'inspiration.error.filesystem')
            return self.text(json.dumps(result),'application/json',False)
        if self.path in ('/claude-job', '/claude-job-cancel'):
            if not self.trusted(write=True):return
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:return self.send_error(400)
            if self.headers.get('X-Studio-Action')!=self.path[1:]:return self.send_error(403)
            if self.headers.get_content_type()!='application/json':return self.send_error(415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:return self.send_error(413)
                body=json.loads(self.rfile.read(size))
                if self.path=='/claude-job':
                    if not isinstance(body,dict) or 'task' not in body or set(body)-{'project','task','reference'}:raise ValueError()
                    result,status=claude_runner.start(body.get('project'),body['task'],body.get('reference')),202
                else:
                    if not isinstance(body,dict) or set(body)!={'job'}:raise ValueError()
                    claude_runner.cancel(body['job'])
                    result,status=claude_runner.status(body['job']),200
            except json.JSONDecodeError:return self.json_error(400,'claude.invalid-request')
            except claude_runner.RunnerError as error:return self.json_error(error.status,error.message_key,error.details)
            except (ValueError,TypeError,KeyError):return self.json_error(400,'claude.invalid-request')
            except OSError:return self.json_error(503,'claude.failed')
            return self.text(json.dumps(result),'application/json',False,status)
        if not self.trusted(write=True): return
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            return self.send_error(400)
        if self.path == '/feedback-note':
            if self.headers.get('X-Studio-Action')!='feedback-note':return self.send_error(403)
            if self.headers.get_content_type()!='application/json':return self.send_error(415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:return self.send_error(413)
                result=change_feedback(json.loads(self.rfile.read(size)))
            except json.JSONDecodeError:return self.json_error(400,'Use a valid JSON feedback change.')
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Feedback could not be changed. Existing notes and your draft are preserved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/feedback-link':
            raw=self.json_request('feedback-link',1048576)
            if raw is None:return
            try:
                result=save_feedback_link(json.loads(raw))
            except json.JSONDecodeError:return self.json_error(400,'Use a valid JSON feedback selection.')
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The feedback link could not be prepared. Your saved notes are preserved.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/feedback':
            raw=self.json_request('feedback',16384)
            if raw is None:return
            try:
                body=json.loads(raw)
                result=save_feedback(body)
            except json.JSONDecodeError:return self.json_error(400,'Use a valid JSON feedback request.')
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Feedback could not be saved. Existing notes were preserved; try again.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/references':
            if self.headers.get('X-Studio-Action')!='reference':return self.send_error(403)
            if self.headers.get_content_type()!='application/json':return self.send_error(415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:return self.send_error(413)
                body=json.loads(self.rfile.read(size))
            except (ValueError,TypeError):return self.json_error(400,'Use a valid JSON reference request.')
            try:result=save_reference(body)
            except IntakeError as error:return self.json_error(error.status,str(error))
            except ReviewError as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The reference could not be saved. Check the local library and try again.')
            return self.text(json.dumps(result),'application/json',False)
        if self.path == '/review-action':
            host = self.headers.get('Host', '')
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if (host not in allowed or self.headers.get('Origin') != 'http://' + host or
                self.headers.get('Sec-Fetch-Site') == 'cross-site' or
                self.headers.get('X-Studio-Action') != 'review'):
                return self.send_error(403)
            if self.headers.get_content_type() != 'application/json':
                return self.send_error(415)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192: return self.send_error(413)
                body = json.loads(self.rfile.read(size))
            except (ValueError, TypeError):
                return self.json_error(400, 'review.error.invalidJson')
            try:
                result = apply_decision(body)
            except ReviewError as error:
                return self.json_error(error.status, error.message_key or str(error))
            except (ValueError, TypeError, KeyError, OSError):
                return self.json_error(503, 'review.error.metadataNotSaved')
            return self.text(json.dumps(result), 'application/json', False)
        if self.path != '/context': return self.send_error(404)
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.send_error(403)
        if self.headers.get_content_type() != 'application/json':
            return self.send_error(415, 'Use application/json.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536: return self.send_error(413)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict) or set(body) - {'ids', 'notes', 'mode'}:
                raise ValueError()
            base_url = origin or f'http://127.0.0.1:{self.server.server_port}'
            text = context_handoff(body.get('ids'), body.get('notes'), body.get('mode', 'short'), base_url=base_url)
        except (ValueError, TypeError, KeyError):
            return self.send_error(400, 'Choose valid references, examples and notes (1000 characters per field).')
        return self.text(text, 'text/plain; charset=utf-8', False)

    def do_PUT(self):
        route = urlparse(self.path)
        if route.path == '/inspiration-file': return self.put_inspiration(route)
        if route.path != '/materials': return self.send_error(404)
        if not self.trusted(write=True): return
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1: return self.send_error(400)
        if self.headers.get('X-Studio-Action') != 'materials': return self.send_error(403)
        query = parse_qs(route.query, keep_blank_values=True)
        if set(query) != {'project', 'name'} or any(len(v) != 1 for v in query.values()):
            return self.json_error(400, 'materials.error.invalidRequest')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send_error(400)
        try:
            item = upload_material(query['project'][0], query['name'][0], self.rfile, length)
        except MaterialsError as error:
            return self.json_error(error.status, error.message_key)
        except (OSError, ValueError, TypeError, KeyError):
            return self.json_error(503, 'materials.error.filesystem')
        return self.text(json.dumps(item), 'application/json', False, 201)

    def put_inspiration(self, route):
        """Task 13: PUT /inspiration-file?name=<file>[&title=&creator=&note=] adds a new
        reference from a dropped video; ?name=<file>&reference=<id> adds the file to an
        existing reference. Same write guards and streaming as PUT /materials."""
        if not self.trusted(write=True): return
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1: return self.send_error(400)
        if self.headers.get('X-Studio-Action') != 'inspiration-file': return self.send_error(403)
        query = parse_qs(route.query, keep_blank_values=True)
        details = {'title', 'creator', 'note'}
        if ('name' not in query or any(len(v) != 1 for v in query.values()) or
                set(query) - {'name', 'reference'} - details or ('reference' in query and set(query) & details)):
            return self.json_error(400, 'inspiration.error.invalidRequest')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send_error(400)
        try:
            result = inspiration.upload(self.rfile, length, query['name'][0], query.get('reference', [None])[0],
                                        **{k: query[k][0] for k in details if k in query})
        except inspiration.InspirationError as error:
            return self.json_error(error.status, error.message_key, error.details)
        except (OSError, ValueError, TypeError, KeyError):
            return self.json_error(503, 'inspiration.error.filesystem')
        return self.text(json.dumps(result), 'application/json', False, 201)

    def do_HEAD(self): self.respond(head=True)
    def do_GET(self): self.respond(head=False)
    def respond(self, head=False):
        if not self.trusted(): return
        route=urlparse(self.path); path=unquote(route.path)
        if path in {'/script-brief', '/writing-voice', '/script-hooks', '/script-feedback'}:
            try:
                query = parse_qs(route.query, keep_blank_values=True)
                if path == '/writing-voice':
                    if query: return self.send_error(400)
                    result = voice_current()
                elif path == '/script-brief':
                    if set(query) != {'project'} or len(query['project']) != 1: return self.send_error(400)
                    result = brief_current(query['project'][0])
                else:
                    optional = 'version' if path == '/script-hooks' else 'request'
                    allowed = {'project', optional} if path == '/script-hooks' else {'project', 'request', 'revision'}
                    if ('project' not in query or set(query) - allowed or ('revision' in query and 'request' not in query) or
                            any(len(v) != 1 for v in query.values())): return self.send_error(400)
                    result = (hooks_current(query['project'][0], query.get(optional, [None])[0]) if path == '/script-hooks'
                              else script_feedback_current(query['project'][0], query.get(optional, [None])[0], query.get('revision', [None])[0]))
                return self.text(json.dumps(result), 'application/json', head)
            except (FeedbackError, ReviewError) as error: return self.json_error(error.status, str(error))
            except (OSError, ValueError, TypeError, KeyError): return self.json_error(503, 'Writing context is unavailable. Your existing files are preserved.')
        if path=='/materials':
            if not self.trusted():return
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)!={'project'} or len(query['project'])!=1:return self.send_error(400)
                return self.text(json.dumps({'items':list_materials(query['project'][0])}),'application/json',head)
            except MaterialsError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'materials.error.filesystem')
        if path=='/material-library':
            if not self.trusted():return
            try:
                if route.query:return self.send_error(400)
                return self.text(json.dumps({'items':list_library()}),'application/json',head)
            except MaterialsError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'materials.error.filesystem')
        if path.startswith('/project-materials/'):
            if not self.trusted():return
            try:
                parts=path.strip('/').split('/')
                if len(parts)!=3:raise ValueError()
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)-{'poster'} or any(len(v)!=1 for v in query.values()):return self.send_error(400)
                # T9b: ?poster=1 answers a JPEG poster frame instead of the raw bytes --
                # same confinement and lock as the byte route (material_poster_path() calls
                # file_path() internally before ever touching ffmpeg). Generation is
                # synchronous and time-boxed (posters.POSTER_TIMEOUT per ffmpeg/ffprobe call,
                # see posters.py); a poster that can't be made in time (or a non-video
                # material) answers 404, same as a missing file, so the UI's placeholder
                # icon takes over rather than hanging.
                if query.get('poster')==['1']:
                    poster=material_poster_path(parts[1],parts[2])
                    if poster is None:return self.send_error(404)
                    return self.file(poster,head,content_type='image/jpeg')
                target,mime=material_file_path(parts[1],parts[2])
            except MaterialsError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.send_error(404)
            return self.file(target,head,content_type=mime)
        if path=='/claude-job':
            # ?id=<job> -> that job; ?project=<id> / ?reference=<id> -> the newest job for it (Task 15:
            # the project page resumes a running job's progress after a reload).
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if len(query)!=1 or set(query)-{'id','project','reference'} or any(len(v)!=1 for v in query.values()):return self.send_error(400)
                if 'id' in query:result=claude_runner.status(query['id'][0])
                else:result=claude_runner.latest(query.get('project',[None])[0],query.get('reference',[None])[0])
                return self.text(json.dumps(result),'application/json',head)
            except claude_runner.RunnerError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'claude.failed')
        if path=='/claude-job-log':
            # Task 15: the quiet "copy details for support" link. Only a known job's own log, never a path.
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if 'id' not in query or set(query)-{'id','lines'} or any(len(v)!=1 for v in query.values()):return self.send_error(400)
                lines=query.get('lines',[str(claude_runner.LOG_LINES)])[0]
                if not re.fullmatch(r'[0-9]{1,3}',lines):return self.json_error(400,'claude.invalid-request')
                return self.text(json.dumps({'log':claude_runner.log_tail(query['id'][0],int(lines))}),'application/json',head)
            except claude_runner.RunnerError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'claude.failed')
        if path=='/claude-request':
            # Task 15: the "copy to chat" fallback text for one project, in the UI language.
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)!={'project'} or len(query['project'])!=1:return self.send_error(400)
                return self.text(json.dumps({'text':starter_request_text(query['project'][0])}),'application/json',head)
            except LookupError:return self.json_error(404,'claude.unknown-project')
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'claude.failed')
        if path=='/style-card':
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)!={'reference'} or len(query['reference'])!=1:return self.send_error(400)
                return self.text(json.dumps(inspiration.card(query['reference'][0])),'application/json',head)
            except inspiration.InspirationError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'inspiration.error.filesystem')
        if path=='/looks':
            if not self.trusted():return
            try:
                if route.query:return self.send_error(400)
                return self.text(json.dumps({'items':list_looks()}),'application/json',head)
            except LookError as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Looks are unavailable.')
        if path=='/effects':
            if not self.trusted():return
            try:
                if route.query:return self.send_error(400)
                return self.text(json.dumps(list_effects()),'application/json',head)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'effects.loadError')
        if path.startswith('/look-files/'):
            if not self.trusted():return
            try:
                parts=path.strip('/').split('/')
                if len(parts)!=3:raise ValueError()
                target=look_file_path(parts[1],parts[2])
            except LookError as error:return self.send_error(error.status)
            except (OSError,ValueError,TypeError,KeyError):return self.send_error(404)
            return self.file(target,head)
        if path=='/choices':
            if not self.trusted():return
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)!={'project'} or len(query['project'])!=1:return self.send_error(400)
                return self.text(json.dumps(choices_current(query['project'][0])),'application/json',head)
            except ChoicesError as error:return self.json_error(error.status,error.message_key)
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'choices.error.filesystem')
        if path=='/project-tools':
            if not self.trusted():return
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                if set(query)!={'project','artifact'} or any(len(v)!=1 for v in query.values()):return self.send_error(400)
                return self.text(json.dumps(project_tools_state(query['project'][0],query['artifact'][0])),'application/json',head)
            except ToolsError as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The project tools are unavailable. Your work is preserved.')
        if path=='/reference-notes':
            if not self.trusted():return
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                return self.text(json.dumps(reference_notes_state(query.get('id',[''])[0],query.get('example',[None])[0])),'application/json',head)
            except (NoteError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Reference notes are unavailable. Existing notes are preserved.')
        if path=='/reference-visibility':
            if not self.trusted():return
            try:return self.text(json.dumps(visibility_state(parse_qs(route.query).get('id',[''])[0])),'application/json',head)
            except (IntakeError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'The reference is unavailable.')
        if path=='/project-script':
            if not self.trusted():return
            try:
                query=parse_qs(route.query,keep_blank_values=True)
                return self.text(json.dumps(script_state(query.get('project',[''])[0],query.get('version',[None])[0])),'application/json',head)
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error))
            except (OSError,ValueError,TypeError,KeyError):return self.json_error(503,'Saved scripts are unavailable. Existing files are preserved.')
        if path=='/feedback':
            if not self.trusted():return
            try:return self.text(json.dumps(feedback_state(parse_qs(route.query).get('project',[''])[0], parse_qs(route.query,keep_blank_values=True).get('selection',[None])[0])),'application/json',head)
            except (FeedbackError,ReviewError) as error:return self.json_error(error.status,str(error)) if not head else self.send_error(error.status)
            except (OSError,ValueError,TypeError,KeyError):return self.send_error(503,'Saved feedback is unavailable.')
        if path=='/reference-state':
            try:return self.text(json.dumps(reference_state(parse_qs(route.query).get('id',[''])[0])),'application/json',head)
            except IntakeError as error:return self.json_error(error.status,str(error)) if not head else self.send_error(error.status)
            except (OSError,ValueError,TypeError,KeyError):return self.send_error(503,'The reference details are unavailable.')
        if path == '/projects.json' or path.startswith('/project-files/') or path.startswith('/project-assets/'):
            host = self.headers.get('Host', '')
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if host not in allowed or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send_error(403)
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                return self.send_error(403)
            try:
                if path == '/projects.json':
                    return self.text(json.dumps(public_index()), 'application/json', head)
                parts = path.strip('/').split('/')
                if len(parts) != 3: raise ValueError()
                filename, mime = (get_asset if path.startswith('/project-assets/') else get_file)(parts[1], parts[2])
                # T9b: ?poster=1 on a video project asset answers a generated JPEG poster
                # frame (tone-mapped to SDR for HEVC/HLG iPhone footage) instead of the
                # video bytes, so the review player's <video poster> is never a black box.
                if path.startswith('/project-assets/') and parse_qs(route.query).get('poster') == ['1']:
                    if not mime.startswith('video/'): return self.send_error(404)
                    poster = get_asset_poster(parts[1], parts[2])
                    if poster is None: return self.send_error(404)
                    return self.file(poster, head, content_type='image/jpeg')
                return self.file(filename, head, content_type=mime)
            except (KeyError, IndexError, StopIteration, ValueError, OSError):
                return self.send_error(404, 'This project checkpoint is unavailable. Read its current project notes.')
        if path=='/api/health':return self.text(json.dumps({'app':'ai-video-studio','root':str(BASE),'pid':os.getpid()}),'application/json',head)
        if path=='/catalog.json':return self.text(json.dumps(catalog()),'application/json',head)
        if path=='/site-settings.json':return self.text(json.dumps(site_settings()),'application/json',head)
        if path=='/ui-language':return self.text(json.dumps({'language':ui_language()}),'application/json',head)
        if path=='/ui-motion':return self.text(json.dumps({'motion':ui_motion()}),'application/json',head)
        if path=='/ui-welcome':return self.text(json.dumps({'welcome_seen':welcome_seen()}),'application/json',head)
        if path=='/addons':return self.text(json.dumps(addons_state()),'application/json',head)
        if path=='/brief':
            try:
                ids=parse_qs(route.query).get('ids',[''])[0].split(',')
                return self.text(reference_brief(ids),'text/plain; charset=utf-8',head)
            except (KeyError,ValueError):return self.send_error(400,'Choose valid video, technique and example ids.')
        if path.startswith('/media/'):
            e=entry_map().get(path.removeprefix('/media/'))
            try:
                return self.file(registered_file(STUDIO, e['media_path'], MEDIA), head) if e and e.get('media_path') else self.send_error(404)
            except (ValueError, OSError): return self.send_error(404)
        if path.startswith('/slides/'):
            parts=path.strip('/').split('/')
            try:
                if len(parts)!=3:raise ValueError()
                e=entry_map()[parts[1]]
                if not re.fullmatch(r'0|[1-9][0-9]*', parts[2]): raise ValueError()
                index=int(parts[2])
                if e.get('asset_type')!='carousel' or not 0<=index<len(e['slides']):raise ValueError()
                return self.file(registered_file(STUDIO,e['slides'][index]['path'],MEDIA),head)
            except (KeyError,IndexError,ValueError,OSError):return self.send_error(404)
        if path.startswith('/download/'):
            e=entry_map().get(path.removeprefix('/download/'))
            try:
                return self.file(registered_file(STUDIO,e['archive_path'],{'.zip'}),head) if e and e.get('archive_path') else self.send_error(404)
            except (ValueError, OSError): return self.send_error(404)
        if path.startswith('/notes/'):
            parts=path.strip('/').split('/')
            try:
                if len(parts)!=3 or not re.fullmatch(r'0|[1-9][0-9]*',parts[2]): raise ValueError()
                e=entry_map()[parts[1]]; filename=e['notes'][int(parts[2])]
                return self.file(registered_file(STUDIO,filename,NOTES),head,content_type='text/plain; charset=utf-8')
            except (KeyError,IndexError,ValueError,OSError):return self.send_error(404)
        filename=(BASE/'dist'/('index.html'if path=='/'else path.lstrip('/'))).resolve()
        if not filename.is_relative_to((BASE/'dist').resolve()) or (BASE/'dist').is_symlink():return self.send_error(403)
        return self.file(filename,head)

    def text(self,body,content_type,head,status=200):
        data=body.encode();self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',len(data));self.send_header('Cache-Control','no-cache');self.end_headers()
        if not head:self.wfile.write(data)

    def json_request(self, action, limit):
        """The one write guard for the studio's JSON POST routes (final review M13a): a trusted
        local Host/Origin, exactly one Content-Length and no Transfer-Encoding, this route's
        X-Studio-Action, application/json, and a body of 1..limit bytes. Returns the raw body,
        or None after answering the request itself."""
        if not self.trusted(write=True):return None
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:
            self.send_error(400);return None
        if self.headers.get('X-Studio-Action')!=action:self.send_error(403);return None
        if self.headers.get_content_type()!='application/json':self.send_error(415);return None
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:self.send_error(400);return None
        if not 0<size<=limit:self.send_error(413);return None
        return self.rfile.read(size)

    def json_error(self, status, message, details=None):
        # A known English sentence is answered as its i18n key (server_messages, final review I2).
        data = json.dumps({'error': server_messages.code(message), **(details or {})}).encode()
        self.send_response(status);self.send_header('Content-Type', 'application/json');self.send_header('Content-Length', len(data));self.send_header('Cache-Control', 'no-store');self.end_headers();self.wfile.write(data)

    def file(self,filename,head=False,content_type=None):
        if not filename.is_file():return self.send_error(404)
        size=filename.stat().st_size;start=0;end=size-1;status=200
        request=self.headers.get('Range')
        if request:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',request)
            if not match or not any(match.groups()):return self.range_error(size)
            if match[1]:start=int(match[1]);end=min(int(match[2])if match[2]else end,end)
            else:start=max(0,size-int(match[2]))
            if start>=size or start>end:return self.range_error(size)
            status=206
        # A browser that cancels a video range request (e.g. seeking, or navigating away
        # mid-stream) tears down the socket while we're still writing to it. That's normal
        # client behavior, not a server error: BrokenPipeError/ConnectionResetError (and,
        # on Windows, ConnectionAbortedError -- WinError 10053) are expected here and must
        # stay quiet rather than spam a traceback for every cancelled range request. Headers
        # are included in the guard too, since the same abort can land before the body loop
        # even starts.
        try:
            self.send_response(status);self.send_header('Content-Type',content_type or mimetypes.guess_type(filename)[0]or'application/octet-stream');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',end-start+1);self.send_header('Cache-Control','no-cache')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            if not head:
                with filename.open('rb')as f:
                    f.seek(start);remaining=end-start+1
                    while remaining>0:
                        data=f.read(min(256*1024,remaining))
                        if not data:break
                        self.wfile.write(data);remaining-=len(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

    def range_error(self,size):
        self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers()

def refresh_tool_path():
    # Node/FFmpeg/whisper installed after the window that started us opened are not on our
    # PATH yet (Windows reads PATH once; a fresh Homebrew is not on it either). Pick them up
    # so editing, previews and Send to Claude find them. A no-op elsewhere or on any error.
    try:
        sys.path.insert(0, str(STUDIO / 'scripts'))
        import tools
        return tools.refresh_path()
    except (ImportError, OSError):
        return False

if __name__=='__main__':
    refresh_tool_path()
    from materials import clean_stale_uploads
    clean_stale_uploads()  # temp files of uploads a stopped server never finished (M4)
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4870);args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}'
    # index.html requests launch.js unconditionally (it redirects a double-clicked file://
    # copy of the page to this real server). start.py normally generates dist/launch.js
    # with the live URL before a browser ever loads the page, but it's gitignored -- never
    # shipped or committed -- so running this file directly (without start.py) left it
    # missing and every page load 404'd on it. Write/refresh it here too, so GET /launch.js
    # never 404s no matter how the server was started, and it always carries this run's
    # actual port. The one template (atomic.write_launch_js) is shared with start.py.
    from atomic import write_launch_js
    write_launch_js(BASE/'dist',url)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(json.dumps({'url':url,'app':'ai-video-studio'}),flush=True)
    server.serve_forever()
