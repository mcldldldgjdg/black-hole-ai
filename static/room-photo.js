var PHOTO_SIZE={w:768,h:512},PHOTO_VERSION=3;
var KIND_EN={'диван':'sofa','кровать':'double bed','шкаф':'tall wardrobe with doors','стеллаж':'bookshelf','тв':'TV on a TV stand',
    'стол':'table','стул':'chair','кресло':'armchair','тумба':'nightstand','гарнитур':'kitchen cabinets with countertop',
    'холодос':'refrigerator','лампа':'floor lamp','растен':'potted plant','ковёр':'rug',
    'ванна':'white bathtub','унитаз':'wall-hung toilet','раковина':'washbasin on a vanity cabinet','стиралка':'washing machine'};
var ABSENT_EN={'кровать':'bed','диван':'sofa','шкаф':'wardrobe','тв':'television','гарнитур':'kitchen cabinets','холодос':'refrigerator','ванна':'bathtub','унитаз':'toilet'};
var COLOR_EN={'бел':'white','черн':'black','чёрн':'black','сер':'grey','беж':'beige','коричн':'brown','зел':'green','син':'blue',
    'голуб':'light blue','красн':'red','желт':'yellow','жёлт':'yellow','оранж':'orange','розов':'pink','фиолет':'purple','дерев':'wooden','дуб':'oak'};
var photoQueue=[],photoBusy=false,photoCurrent=null;

function colorOf(name){
    var low=String(name||'').toLowerCase();
    for(var k in COLOR_EN)if(low.indexOf(k)!==-1)return COLOR_EN[k]+' ';
    return'';
}

function describeForPhoto(layout,roomType){
    var items=[],present={};
    layout.items.forEach(function(li){
        var k=kindOf(li.item);present[k]=1;
        var noun=KIND_EN[k];if(!noun)return;
        if(k==='стол'){
            if(li.item.workplace||roomType==='office')noun='computer desk with a monitor';
            else if(roomType==='kitchen')noun='dining table';
            else if(roomType==='living')noun='coffee table';
        }
        if(k==='ванна'&&/душ/i.test(li.item.item))noun='glass shower cabin';
        if(li.item.divider)noun+=' used as a room divider';
        items.push(colorOf(li.item.item)+noun);
        var chairs=chairSpots(li.item,li.dims,roomType).length;
        if(chairs)items.push(chairs===1?(li.item.workplace?'office chair':'chair'):chairs+' chairs');
    });
    if(layout.decor)items.push('pendant lamp','large window');
    var absent=[];
    for(var k in ABSENT_EN)if(!present[k])absent.push(ABSENT_EN[k]);
    return{items:items,absent:absent};
}

var SIDE_NORMAL={front:[0,1],back:[0,-1],left:[-1,0],right:[1,0]};

function photoCamera(layout,roomDims,aspect,ctx){
    var W=roomDims.width,D=roomDims.depth,inset=0.35,out=1.8,best=null;
    var win=layout.decor?new THREE.Vector3(layout.decor.winX,1.5,0.05):null;
    var spots=[[W-inset,D-inset],[inset,D-inset],[W-inset,inset+0.6],[inset,inset+0.6]];
    var exterior=ctx?ctx.exterior:['front','back','left','right'];
    exterior.forEach(function(side){
        var n=SIDE_NORMAL[side],horiz=side==='front'||side==='back';
        [0.3,0.5,0.7].forEach(function(t){
            var x=horiz?W*t:(side==='left'?-out:W+out),z=horiz?(side==='back'?-out:D+out):D*t;
            spots.push([x,z,side]);
        });
    });
    (ctx?ctx.doors:[]).forEach(function(d){
        var n=SIDE_NORMAL[d.side];
        spots.push([d.x+n[0]*0.6,d.z+n[1]*0.6,d.side]);
    });
    spots.forEach(function(sp){
        var solid=layout.items.filter(function(li){return kindOf(li.item)!=='ковёр'});
        if(!sp[2]&&solid.some(function(li){var p=li.pos;return Math.abs(sp[0]-p.x)<p.w/2+0.2&&Math.abs(sp[1]-p.z)<p.d/2+0.2}))return;
        var cam=new THREE.PerspectiveCamera(70,aspect,0.4,Math.hypot(W,D)+out+1);
        cam.position.set(sp[0],1.6,sp[1]);
        cam.lookAt(W/2,1.0,D/2);
        cam.updateMatrixWorld();
        cam.userData.side=sp[2]||null;
        var score=0;
        solid.forEach(function(li){
            var c=new THREE.Vector3(li.pos.x,(li.dims.h||0.8)/2,li.pos.z),dist=c.distanceTo(cam.position),v=c.clone().project(cam);
            var weight=1+Math.min(li.pos.w*li.pos.d,2);
            var visible=v.z<1&&Math.abs(v.x)<0.85&&Math.abs(v.y)<0.9&&dist>1.6;
            score+=visible?weight:-weight;
            if(visible){
                var r=li.pos.rot||0,toCam=new THREE.Vector2(cam.position.x-li.pos.x,cam.position.z-li.pos.z).normalize();
                score+=weight*Math.max(0,Math.sin(r)*toCam.x+Math.cos(r)*toCam.y);
            }
            chairSpots(li.item,li.dims,layout.roomType).forEach(function(spot){
                var w=planToWorld(li,spot.x,spot.z),p=new THREE.Vector3(w.x,0.5,w.z),pv=p.clone().project(cam);
                if(pv.z<1&&Math.abs(pv.x)<1&&Math.abs(pv.y)<1&&p.distanceTo(cam.position)<1.6)score-=1.5;
            });
        });
        var mid=[W/2,D/2],eye=[cam.position.x,cam.position.z];
        solid.forEach(function(li){
            if((li.dims.h||0)<1.2)return;
            var p=li.pos,x0=p.x-p.w/2,x1=p.x+p.w/2,z0=p.z-p.d/2,z1=p.z+p.d/2,t0=0,t1=1,dx=mid[0]-eye[0],dz=mid[1]-eye[1];
            [[-dx,eye[0]-x0],[dx,x1-eye[0]],[-dz,eye[1]-z0],[dz,z1-eye[1]]].forEach(function(c){
                if(c[0]===0){if(c[1]<0)t0=2}else{var r=c[1]/c[0];if(c[0]<0)t0=Math.max(t0,r);else t1=Math.min(t1,r)}
            });
            if(t0<=t1&&t0<1)score-=3;
        });
        if(win&&cam.userData.side!=='back'){var wv=win.clone().project(cam);if(wv.z<1&&Math.abs(wv.x)<0.9&&Math.abs(wv.y)<0.9)score+=1.5}
        if(!best||score>best.score)best={cam:cam,score:score};
    });
    return best.cam;
}

function depthMaterial(near,far){
    return new THREE.ShaderMaterial({
        uniforms:{near:{value:near},far:{value:far}},
        vertexShader:'varying float vDepth;void main(){vec4 mv=modelViewMatrix*vec4(position,1.0);vDepth=-mv.z;gl_Position=projectionMatrix*mv;}',
        fragmentShader:'uniform float near;uniform float far;varying float vDepth;void main(){float d=clamp((vDepth-near)/(far-near),0.0,1.0);gl_FragColor=vec4(vec3(1.0-d),1.0);}',
        side:THREE.DoubleSide
    });
}

function buildStudioScene(rooms){
    var spots=planPackRooms(rooms),scene=new THREE.Scene(),wallMat=null,heights=[],lit=false;
    scene.background=new THREE.Color(0xf4f1ea);
    rooms.forEach(function(room,j){
        if(isBath(room))return;
        var built=buildRoomScene(room.furniture,room.room_dimensions,room.room_type,roomLook(room)),s=spots[j],g=new THREE.Group();
        wallMat=wallMat||built.wallMat;heights.push(room.room_dimensions.height);
        built.helpers.forEach(function(h){h.visible=false});
        ['front','back','left','right'].forEach(function(k){built.walls[k][0].visible=false});
        built.walls.left[1].visible=false;
        built.photoOnly.visible=true;
        Object.keys(built.shells).forEach(function(k){built.shells[k].visible=false});
        built.scene.children.slice().forEach(function(o){
            if(lit&&(o.isAmbientLight||o.isDirectionalLight))return;
            g.add(o);
        });
        lit=true;
        if(s.rot===180){g.rotation.y=Math.PI;g.position.set(s.x+s.w,0,s.y+s.d)}else g.position.set(s.x,0,s.y);
        scene.add(g);
    });
    var H=Math.max.apply(null,heights);
    rooms.forEach(function(room,j){
        if(isBath(room))return;
        var edges=planEdges(spots,j);
        Object.keys(edges).forEach(function(k){
            var e=edges[k];
            e.exterior.concat(e.shared.filter(function(iv){return isBath(rooms[iv[2]])})).forEach(function(iv){
                var len=iv[1]-iv[0],m=new THREE.Mesh(new THREE.PlaneGeometry(len,H),wallMat);
                if(e.horiz){m.position.set((iv[0]+iv[1])/2,H/2,e.at)}else{m.rotation.y=Math.PI/2;m.position.set(e.at,H/2,(iv[0]+iv[1])/2)}
                scene.add(m);
            });
        });
    });
    return scene;
}

function shotStudio(rooms,i){
    var scene=buildStudioScene(rooms),info=studioRoute(rooms)[i];
    var renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    renderer.setPixelRatio(1);renderer.setSize(PHOTO_SIZE.w,PHOTO_SIZE.h,false);
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    var cam=new THREE.PerspectiveCamera(70,PHOTO_SIZE.w/PHOTO_SIZE.h,0.3,30);
    cam.position.set(info.plan.x,1.6,info.plan.z);cam.lookAt(info.plan.tx,1.0,info.plan.tz);cam.updateMatrixWorld();
    var box=new THREE.Box3().setFromObject(scene),far=box.min.distanceTo(box.max)+1;
    cam.far=far;cam.updateProjectionMatrix();
    renderer.render(scene,cam);
    var image=renderer.domElement.toDataURL('image/png');
    var depthMat=depthMaterial(cam.near,cam.far),farMat=new THREE.MeshBasicMaterial({color:0x000000,side:THREE.DoubleSide});
    scene.traverse(function(o){if(o.isMesh)o.material=o.userData.window?farMat:depthMat});
    scene.background=new THREE.Color(0x000000);
    renderer.render(scene,cam);
    var depth=renderer.domElement.toDataURL('image/png');
    renderer.dispose();renderer.forceContextLoss();
    var room=rooms[i],desc=describeForPhoto(computeLayout(room.furniture,room.room_dimensions,room.room_type),room.room_type);
    var present={};
    rooms.forEach(function(r){if(!isBath(r))computeLayout(r.furniture,r.room_dimensions,r.room_type).items.forEach(function(li){present[kindOf(li.item)]=1})});
    desc.absent=Object.keys(ABSENT_EN).filter(function(k){return!present[k]}).map(function(k){return ABSENT_EN[k]});
    return{image:image,depth:depth,items:desc.items,absent:desc.absent,camera:info};
}

function shotRoom(room){
    var rooms=currentResult&&currentResult.rooms,idx=rooms?rooms.indexOf(room):-1;
    if(idx>=0&&currentResult.open_plan&&rooms.length>1&&!isBath(room))return shotStudio(rooms,idx);
    var built=buildRoomScene(room.furniture,room.room_dimensions,room.room_type,roomLook(room));
    var renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    renderer.setPixelRatio(1);renderer.setSize(PHOTO_SIZE.w,PHOTO_SIZE.h,false);
    renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    built.helpers.forEach(function(h){h.visible=false});
    built.photoOnly.visible=true;
    built.scene.fog=null;
    var routed=routeCamera(room),aspect=PHOTO_SIZE.w/PHOTO_SIZE.h;
    var cam=routed?cameraFromInfo(routed,room.room_dimensions,aspect):photoCamera(built.layout,room.room_dimensions,aspect,roomContext(room)),side=cam.userData.side;
    if(side){built.walls[side].forEach(function(o){o.visible=false});built.shells[side].visible=true}
    renderer.render(built.scene,cam);
    var image=renderer.domElement.toDataURL('image/png');
    var depthMat=depthMaterial(cam.near,cam.far),farMat=new THREE.MeshBasicMaterial({color:0x000000,side:THREE.DoubleSide});
    built.scene.traverse(function(o){if(o.isMesh)o.material=o.userData.window?farMat:depthMat});
    built.scene.background=new THREE.Color(0x000000);
    renderer.render(built.scene,cam);
    var depth=renderer.domElement.toDataURL('image/png');
    renderer.dispose();renderer.forceContextLoss();
    var desc=describeForPhoto(built.layout,room.room_type);
    if(side==='back')desc.items=desc.items.filter(function(t){return t!=='large window'});
    return{image:image,depth:depth,items:desc.items,absent:desc.absent,camera:cameraInfo(cam,room.room_dimensions)};
}

function cameraInfo(cam,roomDims){
    var hfov=2*Math.atan(Math.tan(cam.fov*Math.PI/360)*cam.aspect)*180/Math.PI;
    return{x:+cam.position.x.toFixed(2),z:+cam.position.z.toFixed(2),tx:roomDims.width/2,tz:roomDims.depth/2,hfov:+hfov.toFixed(1),side:cam.userData.side||null};
}

function roomContext(room){
    var rooms=currentResult&&currentResult.rooms,i=rooms?rooms.indexOf(room):-1;
    return i>=0&&rooms.length>1?roomPlanContext(rooms,i,!!currentResult.open_plan):null;
}

function routeCamera(room){
    var rooms=currentResult&&currentResult.rooms,i=rooms?rooms.indexOf(room):-1;
    if(i<0||!currentResult.open_plan||rooms.length<2||isBath(room))return null;
    var route=studioRoute(rooms);
    return route?route[i]:null;
}

function cameraFromInfo(info,roomDims,aspect){
    var cam=new THREE.PerspectiveCamera(70,aspect,0.4,Math.hypot(roomDims.width,roomDims.depth)+Math.hypot(info.x-info.tx,info.z-info.tz)+1);
    cam.position.set(info.x,1.6,info.z);cam.lookAt(info.tx,1.0,info.tz);cam.updateMatrixWorld();
    cam.userData.side=info.side||null;
    return cam;
}

function roomCamera(room){
    if(room.photo_camera)return room.photo_camera;
    var routed=routeCamera(room);
    if(routed)return routed;
    var layout=computeLayout(room.furniture,room.room_dimensions,room.room_type);
    return cameraInfo(photoCamera(layout,room.room_dimensions,PHOTO_SIZE.w/PHOTO_SIZE.h,roomContext(room)),room.room_dimensions);
}

function photoSlot(i){return document.querySelector('.room-photo[data-room="'+i+'"]')}

function setPhotoState(i,state,text){
    var slot=photoSlot(i);if(!slot)return;
    var room=currentResult.rooms[i];
    var img=room.image_url?'<img src="'+room.image_url+'" class="generated-image" alt="Визуализация: '+esc(room.room_name)+'">':'';
    var note=state==='busy'?'<div class="photo-status">🎨 '+esc(text||'Рисуем фото по 3D-сцене…')+'</div>':(state==='error'?'<div class="photo-status warn">⚠️ '+esc(text)+'</div>':'');
    var schema=room.image_url&&room.image_source==='3d'&&state!=='busy'?'<div class="cam-schema-wrap"><div class="cam-schema-box"></div><p class="order-note">📐 Схема съёмки: жёлтый сектор — камера фото, бирюзовый — текущий вид 3D'+(roomCamera(room).side?', красный пунктир — стена, убранная на время съёмки (так снимают тесные комнаты в архвизе)':'')+'</p></div>':'';
    slot.innerHTML=img+note+schema+'<button type="button" class="btn-secondary photo-redo" onclick="queueRoomPhoto('+i+',true)"'+(state==='busy'?' disabled':'')+'>🔄 Перерисовать фото по 3D</button>';
    var box=slot.querySelector('.cam-schema-box');
    if(box){renderCameraSchema(box,room);if(current3D)syncViewMarker(current3D.camera,current3D.controls.target)}
}

function queueRoomPhoto(i,force){
    var room=currentResult&&currentResult.rooms[i];
    if(!room||!room.furniture.length||typeof THREE==='undefined')return;
    if(!force&&room.image_source==='3d'&&room.photo_version===PHOTO_VERSION)return;
    if(photoQueue.some(function(q){return q.result===currentResult&&q.i===i}))return;
    photoQueue.push({result:currentResult,i:i});
    setPhotoState(i,'busy','В очереди на отрисовку…');
    nextRoomPhoto();
}

function nextRoomPhoto(){
    if(photoBusy||!photoQueue.length)return;
    var job=photoQueue.shift(),res=job.result,room=res.rooms[job.i];
    photoBusy=true;photoCurrent=job;
    if(res===currentResult)setPhotoState(job.i,'busy');
    var shot;
    try{shot=shotRoom(room)}catch(e){photoBusy=false;photoCurrent=null;setPhotoState(job.i,'error','Не удалось снять 3D-сцену');nextRoomPhoto();return}
    postJSON('/render-room',{image:shot.image,depth:shot.depth,style:res.style,room_type:room.room_type,
        items:shot.items,absent:shot.absent,task_id:res.task_id||null,room_index:job.i,camera:shot.camera,version:PHOTO_VERSION,
        wall_color:roomLook(room).wall,look:roomLook(room).prompt})
        .then(function(d){room.image_url=d.image;room.image_source='3d';room.photo_version=PHOTO_VERSION;room.photo_camera=shot.camera;if(res===currentResult)setPhotoState(job.i,'done')})
        .catch(function(e){if(res===currentResult)setPhotoState(job.i,'error',e.message)})
        .then(function(){photoBusy=false;photoCurrent=null;nextRoomPhoto()});
}

function refreshPhotoSlot(i){
    var waiting=photoQueue.some(function(q){return q.result===currentResult&&q.i===i});
    var drawing=photoCurrent&&photoCurrent.result===currentResult&&photoCurrent.i===i;
    setPhotoState(i,drawing?'busy':(waiting?'busy':'done'),waiting?'В очереди на отрисовку…':null);
}

function queueAllRoomPhotos(){
    if(!currentResult)return;
    currentResult.rooms.forEach(function(r,i){queueRoomPhoto(i,false)});
}

function flyToPhoto(i){
    var room=currentResult&&currentResult.rooms[i];
    if(room&&current3D&&current3D.flyTo)current3D.flyTo(roomCamera(room));
}

function syncViewMarker(cam,target){
    var svg=document.querySelector('.cam-schema-box svg');
    if(!svg)return;
    var vb=svg.viewBox.baseVal,cx=vb.x+vb.width/2,cy=vb.y+vb.height/2,x=cam.position.x,y=cam.position.z,m=0.25;
    var dx=x-cx,dy=y-cy,k=1;
    if(Math.abs(dx)>vb.width/2-m)k=Math.min(k,(vb.width/2-m)/Math.abs(dx));
    if(Math.abs(dy)>vb.height/2-m)k=Math.min(k,(vb.height/2-m)/Math.abs(dy));
    x=cx+dx*k;y=cy+dy*k;
    var ang=Math.atan2(target.z-cam.position.z,target.x-cam.position.x),hfov=2*Math.atan(Math.tan(cam.fov*Math.PI/360)*cam.aspect),len=Math.min(vb.width,vb.height)*0.45;
    var pts=[[x,y]];
    for(var s=0;s<=10;s++){var a=ang-hfov/2+hfov*s/10;pts.push([x+Math.cos(a)*len,y+Math.sin(a)*len])}
    var g=svg.querySelector('.plan-view-cam');
    if(!g){g=document.createElementNS('http://www.w3.org/2000/svg','g');g.setAttribute('class','plan-view-cam plan-cam');svg.appendChild(g)}
    g.innerHTML='<polygon class="plan-cam-cone" points="'+pts.map(function(p){return p[0].toFixed(3)+','+p[1].toFixed(3)}).join(' ')+'"/>'
        +'<g transform="translate('+x+' '+y+') rotate('+(ang*180/Math.PI)+')"><rect class="plan-cam-body" x="-0.32" y="-0.16" width="0.34" height="0.32" rx="0.05"/><path class="plan-cam-body" d="M0.02 -0.08 L0.2 -0.16 L0.2 0.16 L0.02 0.08 Z"/></g>';
}

var COLOR_NAMES=[
    ['#F5F5F3','белые','white'],['#EFE8DC','молочные','off-white'],['#E6D8BF','бежевые','beige'],['#DADAD8','светло-серые','light grey'],['#C0C0BE','светло-серые','light grey'],
    ['#A6A6A6','серые','grey'],['#8C8C8C','серые','grey'],['#6E6E6E','тёмно-серые','dark grey'],['#45474B','графитовые','charcoal'],['#1E1E1E','чёрные','black'],['#9CAF88','шалфейные','sage green'],
    ['#6B7444','оливковые','olive green'],['#2F4A3A','тёмно-зелёные','dark green'],['#A9C6DA','голубые','light blue'],['#5F7F99','серо-синие','slate blue'],
    ['#243659','тёмно-синие','navy blue'],['#C0674A','терракотовые','terracotta'],['#8A3B2F','кирпичные','brick red'],['#CFA24A','горчичные','mustard yellow'],
    ['#D9B3AE','пудровые','blush pink'],['#D4C5B0','бежевые','warm beige'],['#F2C1CB','розовые','pink'],['#6E2E38','бордовые','burgundy'],['#7A5C48','коричневые','brown'],['#B79E84','песочные','taupe']];

function nearestColor(hex){
    var c=parseInt(hex.slice(1),16),r=c>>16,g=(c>>8)&255,b=c&255;
    return COLOR_NAMES.reduce(function(best,n){
        var v=parseInt(n[0].slice(1),16),d=Math.pow(r-(v>>16),2)+Math.pow(g-((v>>8)&255),2)+Math.pow(b-(v&255),2);
        return!best||d<best.d?{d:d,n:n}:best;
    },null).n;
}

function floorLook(room){
    var name=((room.materials||[])[0]||{}).item||'',low=name.toLowerCase();
    if(/т[её]мн|венге|орех|эспрессо|wenge/.test(low))return{hex:'#5a3e2b',ru:'тёмное дерево',en:'dark wood'};
    if(/сер|бетон|микроцемент|графит/.test(low))return{hex:'#8a8784',ru:'серый',en:'grey'};
    if(/плитк|керамогранит|мрамор/.test(low))return{hex:'#cfc8bd',ru:'плитка',en:'light stone tile'};
    if(/бел|бел[её]н|светл|беж|дуб|клён|ясен|сосн/.test(low))return{hex:'#c4a27a',ru:'светлое дерево',en:'light oak wood'};
    return{hex:'#9b7653',ru:'дерево',en:'natural wood'};
}

function roomLook(room){
    var wall=/^#[0-9a-fA-F]{6}$/.test(room.wall_color||'')?room.wall_color.toUpperCase():'#E8DFCF';
    var n=nearestColor(wall),f=floorLook(room);
    return{wall:wall,floor:f.hex,wallName:n[1],floorName:f.ru,prompt:n[2]+' painted walls, '+f.en+' floor'};
}

function setWallColor(i,hex){
    var room=currentResult&&currentResult.rooms[i];
    if(!room||!/^#[0-9a-fA-F]{6}$/.test(hex))return;
    room.wall_color=hex.toUpperCase();
    showRoom(i);
    queueRoomPhoto(i,true);
}
