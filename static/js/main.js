// HERO SLIDER

const slides =
document.querySelectorAll(".hero-slide");

let currentSlide = 0;

function changeSlide(){

    if(slides.length === 0) return;

    slides[currentSlide]
    .classList.remove("active");

    currentSlide =
    (currentSlide + 1)
    % slides.length;

    slides[currentSlide]
    .classList.add("active");

}

setInterval(changeSlide,4000);


// DELETE FUNCTION

function deleteListing(id){

    Swal.fire({

        title:'Delete Listing?',

        text:'This listing will be removed.',

        icon:'warning',

        showCancelButton:true,

        confirmButtonColor:'#ef4444',

        confirmButtonText:'Delete'

    }).then((result)=>{

        if(result.isConfirmed){

            const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
            const form = document.createElement("form");
            form.method = "POST";
            form.action = "/delete/" + id;

            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "_csrf_token";
            input.value = token;

            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();

        }

    });

}


async function filterCategory(name){

    const res = await fetch(`/api/category/${name}`);
    const data = await res.json();

    const container = document.getElementById("listing-container");

    container.innerHTML = "";

    data.forEach(item => {

        container.innerHTML += `
        <div class="card">

            <img src="/static/images/${item.image || 'aesthetic-room-decor.jpg'}" onerror="this.onerror=null; this.src='/static/images/aesthetic-room-decor.jpg';">

            <div class="content">

                <h3>${item.title}</h3>

                <div class="price">₹${item.price}</div>

                <div class="location">📍 ${item.location}</div>

                <a class="map"
                   target="_blank"
                   href="https://www.google.com/maps?q=${item.latitude},${item.longitude}">
                   View on map →
                </a>

            </div>

        </div>
        `;
    });
}


function changeSlide(button,direction){

    const imageBox =
    button.closest(".images");

    const slides =
    imageBox.querySelectorAll(".slide");

    let activeIndex = 0;

    slides.forEach((slide,index)=>{

        if(slide.classList.contains("active-slide")){

            activeIndex = index;

        }

    });

    slides[activeIndex]
    .classList.remove("active-slide");

    activeIndex =
    (activeIndex + direction + slides.length)
    % slides.length;

    slides[activeIndex]
    .classList.add("active-slide");

}
